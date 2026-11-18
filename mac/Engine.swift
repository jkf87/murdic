import Foundation

enum DictationError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        switch self { case .message(let text): return text }
    }
}

// All calls run sequentially on the application's engine queue.
final class Engine {
    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()
    private var buffer = Data()

    func start(config: URL? = nil) throws {
        guard let resources = Bundle.main.resourceURL,
              let python = Bundle.main.object(forInfoDictionaryKey: "DictatePython") as? String else {
            throw DictationError.message("앱 번들 또는 Python 설정을 찾을 수 없습니다.")
        }
        process.executableURL = URL(fileURLWithPath: python)
        process.currentDirectoryURL = resources
        process.arguments = ["-m", "dictate"] + (config.map { ["--config-dir", $0.path] } ?? []) + ["serve"]
        var env = ProcessInfo.processInfo.environment
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        process.environment = env
        process.standardInput = input
        process.standardOutput = output
        try process.run()
        guard try receive()["event"] as? String == "ready" else {
            throw DictationError.message("엔진 시작에 실패했습니다.")
        }
    }

    func transcribe(_ file: URL) throws -> String {
        let request = try JSONSerialization.data(withJSONObject: ["wav": file.path])
        try input.fileHandleForWriting.write(contentsOf: request + Data([10]))
        let reply = try receive()
        guard reply["event"] as? String == "result", let text = reply["text"] as? String else {
            throw DictationError.message(reply["message"] as? String ?? "전사 응답 오류")
        }
        return text
    }

    private func receive() throws -> [String: Any] {
        while !buffer.contains(10) {
            let data = output.fileHandleForReading.availableData
            guard !data.isEmpty else {
                throw DictationError.message("Python 엔진이 종료됐습니다. Python·Murmur·모델 캐시를 확인한 뒤 엔진을 다시 시작하세요.")
            }
            buffer.append(data)
        }
        let newline = buffer.firstIndex(of: 10)!
        let line = buffer.prefix(upTo: newline)
        buffer.removeSubrange(...newline)
        guard let reply = try JSONSerialization.jsonObject(with: line) as? [String: Any] else {
            throw DictationError.message("엔진 응답 형식 오류")
        }
        return reply
    }

    deinit {
        // EOF lets MLX release its resources after the current request.
        try? input.fileHandleForWriting.close()
    }
}
