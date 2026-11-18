import AVFoundation
import CoreAudio

@main
struct MicrophoneTests {
    static func main() throws {
        guard let live = InputDevices.enumerate() else { fatalError("Core Audio enumeration failed") }
        if CommandLine.arguments.count == 4, CommandLine.arguments[1] == "--record" {
            try record(live, name: CommandLine.arguments[2], file: URL(fileURLWithPath: CommandLine.arguments[3]))
            return
        }
        // Compare the enumerated UIDs with devices that have input streams on this Mac.
        let system = AudioObjectID(kAudioObjectSystemObject)
        var address = InputDevices.property(kAudioHardwarePropertyDevices)
        var size: UInt32 = 0
        precondition(AudioObjectGetPropertyDataSize(system, &address, 0, nil, &size) == noErr)
        var ids = [AudioDeviceID](repeating: 0, count: Int(size) / 4)
        if !ids.isEmpty {
            precondition(AudioObjectGetPropertyData(system, &address, 0, nil, &size, &ids) == noErr)
        }
        let inputIDs = ids.filter { id in
            var address = InputDevices.property(kAudioDevicePropertyStreams)
            address.mScope = kAudioDevicePropertyScopeInput
            var size: UInt32 = 0
            return AudioObjectGetPropertyDataSize(id, &address, 0, nil, &size) == noErr && size > 0
        }
        precondition(Set(inputIDs) == Set(live.devices.map(\.id)))
        precondition(Set(live.devices.map(\.uid)).count == live.devices.count)

        let name = "murdic.tests." + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        let a = Microphone(id: 1, uid: "a", name: "Built-in")
        let b = Microphone(id: 2, uid: "b", name: "USB")
        let both = InputDevices(devices: [a, b], defaultID: a.id)
        let selection = MicrophoneSelection(defaults: defaults)
        precondition(selection.update(both) == nil && selection.active == a)
        precondition(selection.update(InputDevices(devices: [a, b], defaultID: b.id)) == nil && selection.active == b)
        selection.select(b)
        let restored = MicrophoneSelection(defaults: defaults)
        let replugged = Microphone(id: 9, uid: b.uid, name: b.name)
        precondition(restored.update(InputDevices(devices: [a, replugged], defaultID: a.id)) == nil)
        precondition(restored.active == replugged)
        precondition(restored.update(InputDevices(devices: [a], defaultID: a.id)) == "USB")
        precondition(restored.active == a && restored.pinnedUID == nil)
        precondition(restored.update(both) == nil && restored.active == a)
        precondition(MicrophoneSelection(defaults: defaults).pinnedUID == nil)
        precondition(restored.update(InputDevices()) == nil && restored.active == nil)
        print("Core Audio inputs: \(live.devices.count); default, UID restore, disconnect and reconnect checks passed.")
    }

    // Optional hardware check. Play the Korean fixture through the current speakers
    // after capture is running so that the selected physical mic hears the prompt.
    static func record(_ live: InputDevices, name: String, file: URL) throws {
        guard let mic = live.devices.first(where: { $0.name == name }) else {
            throw DictationError.message("마이크 목록: " + live.devices.map(\.name).joined(separator: ", "))
        }
        let capture = MicrophoneCapture(mic, url: file)
        var done = false
        var failure: Error?
        capture.onFailure = { error in failure = error; done = true }
        capture.start {
            let player = Process()
            player.executableURL = URL(fileURLWithPath: "/usr/bin/afplay")
            player.arguments = ["build/sample.wav"]
            player.terminationHandler = { _ in
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                    let release = ProcessInfo.processInfo.systemUptime
                    capture.stop { result in
                        do {
                            let peak = try result.get()
                            let ms = (ProcessInfo.processInfo.systemUptime - release) * 1000
                            print("\(mic.name): max RMS \(peak) dBFS; WAV finalized in \(Int(ms)) ms")
                        } catch { failure = error }
                        done = true
                    }
                }
            }
            do { try player.run() } catch { failure = error; done = true }
        }
        let deadline = Date().addingTimeInterval(20)
        while !done && Date() < deadline { RunLoop.current.run(until: Date().addingTimeInterval(0.02)) }
        if let failure { throw failure }
        guard done else { throw DictationError.message("마이크 실측 시간 초과") }
    }
}
