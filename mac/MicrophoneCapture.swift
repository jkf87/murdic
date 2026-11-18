import AVFoundation
import Accelerate

// The control queue serializes opening and closing hardware across utterances.
// Sample delivery/file I/O never waits on the main queue.
final class MicrophoneCapture: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate {
    private static let control = DispatchQueue(label: "murdic.microphone.control")
    private let samples = DispatchQueue(label: "murdic.microphone.samples")
    private let session = AVCaptureSession()
    private let output = AVCaptureAudioDataOutput()
    let url: URL?
    let microphone: Microphone
    var isTest: Bool { url == nil }

    private let pcm = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16000,
                                    channels: 1, interleaved: true)!
    private var file: AVAudioFile?
    static let quietDB: Float = -65
    private var maxDB: Float = -160
    private var scratch: [Float] = []
    private var lastMeter: TimeInterval = 0
    private var failure: Error?
    private let stopLock = NSLock()
    private var stopRequested = false
    private var stopping: Bool { stopLock.withLock { stopRequested } }
    private var runtimeObserver: NSObjectProtocol?
    var onLevel: ((Float) -> Void)?
    var onFailure: ((Error) -> Void)?

    init(_ microphone: Microphone, url: URL?) {
        self.microphone = microphone
        self.url = url
    }

    func start(onStarted: @escaping () -> Void) {
        Self.control.async {
            do {
                guard !self.stopping else { return }
                guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized,
                      let device = AVCaptureDevice(uniqueID: self.microphone.uid), device.isConnected else {
                    throw DictationError.message("마이크 연결 및 권한을 확인하세요.")
                }
                let input = try AVCaptureDeviceInput(device: device)
                guard self.session.canAddInput(input) else { throw DictationError.message("마이크를 열 수 없습니다.") }
                self.session.addInput(input)
                guard self.session.canAddOutput(self.output) else { throw DictationError.message("녹음 출력을 열 수 없습니다.") }
                self.session.addOutput(self.output)
                self.output.audioSettings = self.pcm.settings
                if let url = self.url {
                    self.file = try AVAudioFile(forWriting: url, settings: self.pcm.settings,
                                                commonFormat: .pcmFormatInt16, interleaved: true)
                }
                self.output.setSampleBufferDelegate(self, queue: self.samples)
                self.runtimeObserver = NotificationCenter.default.addObserver(
                    forName: AVCaptureSession.runtimeErrorNotification, object: self.session, queue: nil
                ) { [weak self] note in
                    let error = note.userInfo?[AVCaptureSessionErrorKey] as? Error
                        ?? DictationError.message("마이크 연결이 중단됐습니다.")
                    self?.failed(error)
                }
                guard !self.stopping else { return }
                self.session.startRunning()
                guard self.session.isRunning else { throw DictationError.message("마이크를 시작할 수 없습니다.") }
                DispatchQueue.main.async { onStarted() }
            } catch {
                self.samples.sync { self.failure = error }
                self.failed(error)
            }
        }
    }

    private func failed(_ error: Error) {
        DispatchQueue.main.async { self.onFailure?(error) }
    }

    // Release the capture device and finalize the WAV header before handing it to Python.
    func stop(_ completion: @escaping (Result<Float, Error>) -> Void) {
        stopLock.withLock { stopRequested = true }
        Self.control.async {
            if let observer = self.runtimeObserver { NotificationCenter.default.removeObserver(observer) }
            if self.session.isRunning { self.session.stopRunning() }
            self.output.setSampleBufferDelegate(nil, queue: nil)
            let result: Result<Float, Error> = self.samples.sync {
                self.file = nil
                return self.failure.map { .failure($0) } ?? .success(self.maxDB)
            }
            DispatchQueue.main.async { completion(result) }
        }
    }

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard failure == nil, sampleBuffer.numSamples > 0 else { return }
        let count = AVAudioFrameCount(sampleBuffer.numSamples)
        do {
            guard let desc = sampleBuffer.formatDescription,
                  let format = CMAudioFormatDescriptionGetStreamBasicDescription(desc)?.pointee,
                  format.mFormatID == kAudioFormatLinearPCM, format.mSampleRate == 16000,
                  format.mChannelsPerFrame == 1, format.mBitsPerChannel == 16,
                  let buffer = AVAudioPCMBuffer(pcmFormat: pcm, frameCapacity: count) else {
                throw DictationError.message("마이크 출력 형식을 변환할 수 없습니다.")
            }
            buffer.frameLength = count
            guard CMSampleBufferCopyPCMDataIntoAudioBufferList(sampleBuffer, at: 0, frameCount: Int32(count),
                        into: buffer.mutableAudioBufferList) == noErr else {
                throw DictationError.message("마이크 샘플을 읽을 수 없습니다.")
            }
            try file?.write(from: buffer)
            // vDSP reads the Int16 samples into reusable scratch space at native speed.
            let values = UnsafeBufferPointer(start: buffer.int16ChannelData![0], count: Int(count))
            if scratch.count != values.count { scratch = Array(repeating: 0, count: values.count) }
            vDSP.convertElements(of: values, to: &scratch)
            let rms = vDSP.rootMeanSquare(scratch)
            let db = 20 * log10(max(rms / 32768, 0.00000001))
            maxDB = max(maxDB, db)
            let now = ProcessInfo.processInfo.systemUptime
            if now - lastMeter >= 0.075 {
                lastMeter = now
                DispatchQueue.main.async { self.onLevel?(db) }
            }
        } catch {
            failure = error
            failed(error)
        }
    }
}
