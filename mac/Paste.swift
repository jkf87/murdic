import AppKit

final class PasteTransaction {
    private let board: NSPasteboard
    private let saved: [NSPasteboardItem]
    private var ownedChange = -1

    init(board: NSPasteboard, text: String) throws {
        let original = board.changeCount
        var copies: [NSPasteboardItem] = []
        // Best effort: some apps put promised/lazy types on the clipboard whose data can no
        // longer be read (the source app quit, file promises, …). Skip those types instead of
        // refusing to dictate; whatever is readable is restored after the paste.
        for item in board.pasteboardItems ?? [] {
            let copy = NSPasteboardItem()
            var kept = 0
            for type in item.types {
                if let data = item.data(forType: type), copy.setData(data, forType: type) { kept += 1 }
            }
            if kept > 0 { copies.append(copy) }
        }
        guard board.changeCount == original else {
            throw DictationError.message("클립보드가 바뀌어 입력을 중단했습니다.")
        }
        self.board = board
        saved = copies
        ownedChange = board.clearContents()
        guard board.setString(text, forType: .string) else {
            restore()
            throw DictationError.message("텍스트를 클립보드에 넣을 수 없습니다.")
        }
        ownedChange = board.changeCount
    }

    func restore() {
        guard ownedChange == board.changeCount else { return }
        ownedChange = -1
        board.clearContents()
        if !saved.isEmpty { board.writeObjects(saved) }
    }
}

func postPaste(to pid: pid_t) throws {
    guard AXIsProcessTrusted(),
          let down = CGEvent(keyboardEventSource: nil, virtualKey: 9, keyDown: true),
          let up = CGEvent(keyboardEventSource: nil, virtualKey: 9, keyDown: false) else {
        throw DictationError.message("손쉬운 사용 권한을 확인하세요.")
    }
    for event in [down, up] {
        event.flags = .maskCommand
        event.postToPid(pid)
    }
}
