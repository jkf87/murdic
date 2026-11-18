import AppKit
import AVFoundation
import OSLog

private enum Hotkey: String, CaseIterable {
    case option = "오른쪽 Option"
    case control = "오른쪽 Control"
    var code: UInt16 { self == .option ? 61 : 62 }
    // Side-specific NX_DEVICERALTKEYMASK / NX_DEVICERCTLKEYMASK from IOLLEvent.h.
    var mask: UInt { self == .option ? 0x40 : 0x2000 }
}

final class App: NSObject, NSApplicationDelegate {
    static let reopen = Notification.Name("local.murmur.dictate.showSettings")
    private enum State { case idle, loading, ready, recording, processing, pasting, failed }
    private var state = State.idle
    private let queue = DispatchQueue(label: "dictate.engine")
    private var engine = Engine()
    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let menu = NSMenu()
    private let status = NSMenuItem()
    private let overlay = Overlay()
    private let settings = Settings()
    private var permissionTimer: Timer?
    private var lastPermissionState: [Bool] = []
    private var monitors: [Any] = []
    private var held = false
    private var key = Hotkey(rawValue: UserDefaults.standard.string(forKey: "hotkey") ?? "") ?? .option
    private var recorder: AVAudioRecorder?
    private var meter: Timer?
    private var target: NSRunningApplication?
    private var transaction: PasteTransaction?
    private let config = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/murdic")
    private let temp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    private var wav: URL { temp.appendingPathComponent("recording.wav") }

    func applicationDidFinishLaunching(_ note: Notification) {
        DistributedNotificationCenter.default().addObserver(forName: Self.reopen, object: nil, queue: .main) { [weak self] _ in
            self?.showSettings()
        }
        item.button?.title = "murdic"
        if let url = Bundle.main.url(forResource: "murdic", withExtension: "icns"),
           let icon = NSImage(contentsOf: url) {
            icon.size = NSSize(width: 18, height: 18)
            item.button?.image = icon
            item.button?.imagePosition = .imageLeading
        }
        item.menu = menu
        menu.addItem(status)
        let keys = NSMenu()
        for option in Hotkey.allCases {
            let entry = NSMenuItem(title: option.rawValue, action: #selector(selectKey(_:)), keyEquivalent: "")
            entry.target = self
            entry.state = option == key ? .on : .off
            keys.addItem(entry)
        }
        menu.addItem(withTitle: "단축키", action: nil, keyEquivalent: "").submenu = keys
        for (title, action) in [("설정 및 권한…", #selector(showSettings)), ("힌트·설정 폴더 열기", #selector(openConfig)),
                                ("엔진 다시 시작", #selector(restart)), ("종료", #selector(quit))] {
            menu.addItem(withTitle: title, action: action, keyEquivalent: "").target = self
        }
        status.title = "모델 준비 중…"
        showSettings()
        do {
            try FileManager.default.createDirectory(at: temp, withIntermediateDirectories: false,
                                                    attributes: [.posixPermissions: 0o700])
            let fm = FileManager.default
            let previous = config.deletingLastPathComponent().appendingPathComponent("MurmurDictate")
            if !fm.fileExists(atPath: config.path), fm.fileExists(atPath: previous.path) {
                try fm.copyItem(at: previous, to: config)
            } else {
                try fm.createDirectory(at: config, withIntermediateDirectories: true)
            }
            let hints = config.appendingPathComponent("hints.txt")
            if !FileManager.default.fileExists(atPath: hints.path) {
                try Data().write(to: hints, options: .withoutOverwriting)
            }
        } catch { report(error.localizedDescription); return }
        refreshPermissions()
        permissionTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            self?.refreshPermissions()
        }
        let workspace = NSWorkspace.shared.notificationCenter
        workspace.addObserver(self, selector: #selector(interrupted), name: NSWorkspace.willSleepNotification, object: nil)
        workspace.addObserver(self, selector: #selector(interrupted), name: NSWorkspace.sessionDidResignActiveNotification, object: nil)
        workspace.addObserver(self, selector: #selector(focusChanged), name: NSWorkspace.didActivateApplicationNotification, object: nil)
        restart()
        if !AXIsProcessTrusted(), !UserDefaults.standard.bool(forKey: "requestedSignedAccessibility") {
            UserDefaults.standard.set(true, forKey: "requestedSignedAccessibility")
            DispatchQueue.main.async { self.settings.requestAccess() }
        }
    }

    private func installMonitors() {
        for monitor in monitors { NSEvent.removeMonitor(monitor) }
        monitors.removeAll()
        let mask: NSEvent.EventTypeMask = [.flagsChanged, .keyDown]
        if let global = NSEvent.addGlobalMonitorForEvents(matching: mask, handler: { [weak self] in self?.handle($0) }) {
            monitors.append(global)
        }
        if let local = NSEvent.addLocalMonitorForEvents(matching: mask, handler: { [weak self] event in
            self?.handle(event); return event
        }) { monitors.append(local) }
    }

    private func handle(_ event: NSEvent) {
        if event.type == .keyDown {
            if state == .recording { cancelRecording() }
            return
        }
        guard event.keyCode == key.code else { return }
        let down = event.modifierFlags.rawValue & key.mask != 0
        guard down != held else { return }
        held = down
        if down && state == .ready { begin() }
        if !down && state == .recording { finish() }
    }

    @objc private func selectKey(_ sender: NSMenuItem) {
        guard let selected = Hotkey(rawValue: sender.title) else { return }
        if state == .recording { cancelRecording() }
        held = false
        key = selected
        UserDefaults.standard.set(key.rawValue, forKey: "hotkey")
        sender.menu?.items.forEach { $0.state = $0 === sender ? .on : .off }
        if state == .ready { ready() }
    }

    @objc private func showSettings() {
        settings.show()
        refreshPermissions()
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showSettings()
        return false
    }

    private func refreshPermissions() {
        let mic = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
        let trusted = AXIsProcessTrusted()
        let canListen = CGPreflightListenEventAccess()
        let current = [mic, trusted, canListen]
        if current != lastPermissionState {
            lastPermissionState = current
            Logger(subsystem: "local.murmur.dictate", category: "permissions")
                .notice("Microphone: \(mic, privacy: .public), accessibility: \(trusted, privacy: .public), input: \(canListen, privacy: .public)")
            held = false
            if state == .recording { cancelRecording() }
            if trusted || canListen { installMonitors() }
            if state == .ready { ready() }
        }
        settings.refresh(status.title, micAllowed: mic, trusted: trusted, canListen: canListen)
    }

    @objc private func openConfig() { NSWorkspace.shared.open(config) }
    @objc private func quit() { NSApp.terminate(nil) }

    @objc private func restart() {
        guard state == .ready || state == .failed || state == .idle else { return }
        state = .loading
        status.title = "모델 준비 중…"
        engine = Engine()
        let worker = engine
        queue.async {
            do {
                try worker.start()
                DispatchQueue.main.async {
                    self.ready()
                    let mic = AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
                    let ax = AXIsProcessTrusted()
                    Logger(subsystem: "local.murmur.dictate", category: "startup")
                        .notice("Engine ready. Microphone authorized: \(mic, privacy: .public). Accessibility trusted: \(ax, privacy: .public).")
                }
            } catch { DispatchQueue.main.async { self.report(error.localizedDescription) } }
        }
    }

    private func ready() {
        state = .ready
        status.title = AXIsProcessTrusted() && AVCaptureDevice.authorizationStatus(for: .audio) == .authorized
            ? "\(key.rawValue)을 누르고 말하세요" : "받아쓰기를 사용하려면 아래 권한을 허용하세요."
        item.button?.title = "murdic"
        overlay.hide()
    }

    private func report(_ message: String) {
        state = .failed
        status.title = message
        settings.refresh(message, micAllowed: AVCaptureDevice.authorizationStatus(for: .audio) == .authorized,
                         trusted: AXIsProcessTrusted(), canListen: CGPreflightListenEventAccess())
        item.button?.title = "murdic ⚠"
        overlay.hide()
    }

    private func begin() {
        guard AXIsProcessTrusted(), AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {
            ready(); showSettings(); return
        }
        guard let active = NSWorkspace.shared.frontmostApplication,
              active.processIdentifier != ProcessInfo.processInfo.processIdentifier else { return }
        do {
            let session = try AVAudioRecorder(url: wav, settings: [
                AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16000,
                AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false
            ])
            session.isMeteringEnabled = true
            guard session.record() else { throw DictationError.message("마이크를 열 수 없습니다.") }
            recorder = session
            target = active
            state = .recording
            overlay.show("녹음 중 · 키를 떼면 입력", meter: true)
            status.title = "녹음 중"
            let timer = Timer(timeInterval: 0.08, repeats: true) { [weak self] _ in
                session.updateMeters()
                self?.overlay.update(db: session.averagePower(forChannel: 0))
            }
            RunLoop.main.add(timer, forMode: .common)
            meter = timer
        } catch { report(error.localizedDescription) }
    }

    private func stopAudio() {
        meter?.invalidate()
        meter = nil
        recorder?.stop()
        recorder = nil
    }

    private func cancelRecording() {
        stopAudio()
        try? FileManager.default.removeItem(at: wav)
        target = nil
        ready()
    }

    @objc private func interrupted() {
        held = false
        target = nil
        if state == .recording { cancelRecording() }
    }

    @objc private func focusChanged() {
        if let target, !target.isActive {
            self.target = nil
            if state == .recording { cancelRecording() }
        }
    }

    private func finish() {
        let released = ProcessInfo.processInfo.systemUptime
        stopAudio()
        state = .processing
        overlay.show("전사 중…")
        let worker = engine, file = wav
        queue.async {
            let result = Result { try worker.transcribe(file) }
            try? FileManager.default.removeItem(at: file)
            DispatchQueue.main.async {
                do { try self.insert(result.get(), released: released) }
                catch { self.report(error.localizedDescription) }
            }
        }
    }

    private func insert(_ text: String, released: TimeInterval) throws {
        guard !text.isEmpty else { ready(); return }
        guard let target, target.isActive else {
            ready(); status.title = "입력할 앱이 바뀌어 받아쓰기를 취소했습니다."; return
        }
        defer { self.target = nil }
        transaction = try PasteTransaction(board: .general, text: text)
        do { try postPaste(to: target.processIdentifier) }
        catch { transaction?.restore(); transaction = nil; throw error }
        let milliseconds = Int((ProcessInfo.processInfo.systemUptime - released) * 1000)
        state = .pasting
        overlay.hide()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
            self.transaction?.restore()
            self.transaction = nil
            self.ready()
            self.status.title = "최근 ⌘V 전송까지 \(milliseconds) ms"
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        permissionTimer?.invalidate()
        stopAudio()
        transaction?.restore()
        try? FileManager.default.removeItem(at: temp)
        for monitor in monitors { NSEvent.removeMonitor(monitor) }
    }
}
