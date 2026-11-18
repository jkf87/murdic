import AppKit
import AVFoundation

final class Settings: NSObject, NSWindowDelegate {
    private let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 460, height: 260),
                                  styleMask: [.titled, .closable, .miniaturizable],
                                  backing: .buffered, defer: false)
    private let status = NSTextField(wrappingLabelWithString: "")
    private let mic = NSButton()
    private let access = NSButton()
    private let listen = NSButton()
    private let micState = NSTextField(labelWithString: "")
    private let accessState = NSTextField(labelWithString: "")
    private let listenState = NSTextField(labelWithString: "")

    override init() {
        super.init()
        window.title = "murdic"
        window.isReleasedWhenClosed = false
        window.delegate = self
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 12
        status.font = .systemFont(ofSize: 15, weight: .semibold)
        stack.addArrangedSubview(status)
        for (label, button, title, action) in [(micState, mic, "마이크 허용", #selector(requestMic)),
                                              (accessState, access, "손쉬운 사용 설정 열기", #selector(requestAccess)),
                                              (listenState, listen, "입력 모니터링 설정 열기", #selector(requestListen))] {
            button.title = title
            button.target = self
            button.action = action
            button.bezelStyle = .rounded
            let row = NSStackView(views: [label, button])
            row.spacing = 12
            stack.addArrangedSubview(row)
        }
        let hint = NSTextField(wrappingLabelWithString: "권한을 켠 뒤 입력할 앱으로 이동하세요. 이 창을 닫아도 메뉴바에서 받아쓰기가 실행됩니다.")
        hint.textColor = .secondaryLabelColor
        stack.addArrangedSubview(hint)
        let content = window.contentView!
        stack.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -24),
            stack.centerYAnchor.constraint(equalTo: content.centerYAnchor),
            hint.widthAnchor.constraint(lessThanOrEqualTo: stack.widthAnchor),
            status.widthAnchor.constraint(lessThanOrEqualTo: stack.widthAnchor)
        ])
        window.center()
    }

    func show() {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ note: Notification) {
        NSApp.setActivationPolicy(.accessory)
    }

    func refresh(_ text: String, micAllowed: Bool, trusted: Bool, canListen: Bool) {
        status.stringValue = text
        for (label, button, granted, name) in [(micState, mic, micAllowed, "마이크"),
                                                (accessState, access, trusted, "손쉬운 사용"),
                                                (listenState, listen, canListen, "입력 모니터링")] {
            label.stringValue = granted ? "✓  \(name) · 허용됨" : "\(name) · 승인 필요"
            label.textColor = granted ? .systemGreen : .labelColor
            button.isHidden = granted
        }
    }

    private func openPrivacy(_ pane: String) {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_" + pane) {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func requestMic() {
        if AVCaptureDevice.authorizationStatus(for: .audio) == .notDetermined {
            AVCaptureDevice.requestAccess(for: .audio) { _ in }
        } else { openPrivacy("Microphone") }
    }

    @objc func requestAccess() {
        let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        if !AXIsProcessTrustedWithOptions(options) { openPrivacy("Accessibility") }
    }

    @objc private func requestListen() {
        if !CGRequestListenEventAccess() { openPrivacy("ListenEvent") }
    }
}
