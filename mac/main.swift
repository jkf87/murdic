import AppKit

signal(SIGPIPE, SIG_IGN)
let application = NSApplication.shared
application.setActivationPolicy(.accessory)
if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--benchmark" {
    do { try benchmark(URL(fileURLWithPath: CommandLine.arguments[2]).standardizedFileURL) }
    catch {
        FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
        exit(1)
    }
} else {
    // Launch Services can start a second copy from the build directory.
    // The kernel releases this per-user lock even after a crash.
    let lockURL = FileManager.default.temporaryDirectory.appendingPathComponent("local.murmur.dictate.lock")
    let lock = open(lockURL.path, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0o600)
    guard lock >= 0 else { perror("murdic launch lock"); exit(1) }
    guard flock(lock, LOCK_EX | LOCK_NB) == 0 else {
        if errno == EWOULDBLOCK {
            DistributedNotificationCenter.default().postNotificationName(App.reopen, object: nil,
                                                                        userInfo: nil, deliverImmediately: true)
            exit(0)
        }
        perror("murdic launch lock")
        exit(1)
    }
    let delegate = App()
    application.delegate = delegate
    withExtendedLifetime(delegate) { application.run() }
}
