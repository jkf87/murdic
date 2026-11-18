import AppKit

// Exercise the bundled Python process and a native text view without touching
// the user's microphone, frontmost application or general pasteboard.
func benchmark(_ file: URL) throws {
    let fm = FileManager.default
    let config = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try fm.createDirectory(at: config, withIntermediateDirectories: false)
    defer { try? fm.removeItem(at: config) }
    let worker = Engine()
    let clock = ProcessInfo.processInfo
    let start = clock.systemUptime
    try worker.start(config: config)
    print("worker_ready_ms=\(Int((clock.systemUptime - start) * 1000))")
    let view = NSTextView(frame: NSRect(x: 0, y: 0, width: 320, height: 160))
    let board = NSPasteboard.withUniqueName()
    defer { board.releaseGlobally() }
    let binary = NSPasteboard.PasteboardType("local.dictate.fixture")
    let original = Data([0, 1, 255])
    let item = NSPasteboardItem()
    item.setString("원본", forType: .string)
    item.setData(original, forType: binary)
    let second = NSPasteboardItem()
    second.setString("두 번째", forType: .string)
    guard board.writeObjects([item, second]) else { throw DictationError.message("테스트 클립보드 생성 실패") }
    for run in 1...5 {
        view.string = "앞뒤"
        view.setSelectedRange(NSRange(location: 1, length: 0))
        let begin = clock.systemUptime
        let text = try worker.transcribe(file)
        let tx = try PasteTransaction(board: board, text: text)
        guard !text.isEmpty, view.readSelection(from: board, type: .string), view.string == "앞" + text + "뒤" else {
            throw DictationError.message("커서 위치 입력 검증 실패")
        }
        let latency = Int((clock.systemUptime - begin) * 1000)
        tx.restore()
        let restored = board.pasteboardItems ?? []
        guard restored.count == 2, restored[0].data(forType: binary) == original,
              restored[0].string(forType: .string) == "원본", restored[1].string(forType: .string) == "두 번째" else {
            throw DictationError.message("클립보드 복원 검증 실패")
        }
        print("run=\(run) input_ms=\(latency) text=\(text)")
    }
    let tx = try PasteTransaction(board: board, text: "전사")
    board.clearContents()
    board.setString("새 복사", forType: .string)
    tx.restore()
    guard board.string(forType: .string) == "새 복사" else {
        throw DictationError.message("새 복사 보존 검증 실패")
    }
}
