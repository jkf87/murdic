import AppKit

final class Overlay {
    let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 324, height: 60),
                        styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    private let label = NSTextField(labelWithString: "")
    private var dismissal: DispatchWorkItem?
    private let device = NSTextField(labelWithString: "")
    private let level = NSProgressIndicator()

    init() {
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.ignoresMouseEvents = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isOpaque = false
        panel.backgroundColor = .clear
        let background = NSVisualEffectView(frame: panel.contentView!.bounds)
        background.material = .hudWindow
        background.state = .active
        background.wantsLayer = true
        background.layer?.cornerRadius = 12
        background.layer?.masksToBounds = true
        panel.contentView = background
        label.frame = NSRect(x: 16, y: 28, width: 292, height: 18)
        label.lineBreakMode = .byTruncatingTail
        label.font = .systemFont(ofSize: 13, weight: .medium)
        level.frame = NSRect(x: 16, y: 12, width: 105, height: 8)
        level.style = .bar
        level.isIndeterminate = false
        level.maxValue = 1
        background.addSubview(label)
        background.addSubview(level)
        device.frame = NSRect(x: 132, y: 7, width: 176, height: 17)
        device.font = .systemFont(ofSize: 12)
        device.lineBreakMode = .byTruncatingTail
        background.addSubview(device)
    }

    func show(_ text: String, microphone: String? = nil) {
        dismissal?.cancel()
        label.stringValue = text
        device.stringValue = microphone ?? ""
        device.isHidden = microphone == nil
        level.isHidden = microphone == nil
        level.doubleValue = 0
        if let frame = (NSScreen.screens.first { $0.frame.contains(NSEvent.mouseLocation) } ?? NSScreen.main)?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: frame.midX - panel.frame.width / 2, y: frame.minY + 56))
        }
        panel.orderFrontRegardless()
    }

    func update(db: Float) {
        level.doubleValue = min(1, max(0, (Double(db) + 60) / 60))
    }

    func notice(_ text: String) {
        show(text)
        let work = DispatchWorkItem { [weak self] in self?.hide() }
        dismissal = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: work)
    }

    func hide() { dismissal?.cancel(); panel.orderOut(nil) }
}
