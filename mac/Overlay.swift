import AppKit

final class Overlay {
    let panel = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 230, height: 58),
                        styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    private let label = NSTextField(labelWithString: "")
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
        label.frame = NSRect(x: 16, y: 28, width: 198, height: 18)
        label.font = .systemFont(ofSize: 13, weight: .medium)
        level.frame = NSRect(x: 16, y: 12, width: 198, height: 8)
        level.style = .bar
        level.isIndeterminate = false
        level.maxValue = 1
        background.addSubview(label)
        background.addSubview(level)
    }

    func show(_ text: String, meter: Bool = false) {
        label.stringValue = text
        level.isHidden = !meter
        level.doubleValue = 0
        if let frame = (NSScreen.screens.first { $0.frame.contains(NSEvent.mouseLocation) } ?? NSScreen.main)?.visibleFrame {
            panel.setFrameOrigin(NSPoint(x: frame.midX - panel.frame.width / 2, y: frame.minY + 56))
        }
        panel.orderFrontRegardless()
    }

    func update(db: Float) {
        level.doubleValue = min(1, max(0, (Double(db) + 60) / 60))
    }

    func hide() { panel.orderOut(nil) }
}
