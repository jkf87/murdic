// 머딕 키보드 — 🎤를 누르면 머딕 앱을 열어 받아쓰고, 돌아오면 결과를 입력한다.
// 키보드 익스텐션은 마이크를 쓸 수 없어서 녹음·전사는 앱이 한다. 설계: docs/ios-keyboard.md
// App Group ID·키 이름은 Murdic/MurdicShared.m과 같아야 한다.

import UIKit

enum SharedConfig {
  static let appGroup = "group.com.murdic.mobile"
  static let pendingKey = "murdic.pending"
  static let resultKey = "murdic.result"
  static let resultDarwinName = "com.murdic.mobile.result"
  static let resultMaxAgeMs: Double = 5 * 60 * 1000
}

private func nowMs() -> Double { Date().timeIntervalSince1970 * 1000 }

/// App Group에 JSON 문자열 하나씩 저장한다.
struct SharedStore {
  let defaults: UserDefaults

  init?() {
    guard let d = UserDefaults(suiteName: SharedConfig.appGroup) else { return nil }
    defaults = d
  }

  func read(_ key: String) -> [String: Any]? {
    guard let raw = defaults.string(forKey: key), let data = raw.data(using: .utf8),
          let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
    return obj
  }

  func write(_ key: String, _ value: [String: Any]) {
    guard let data = try? JSONSerialization.data(withJSONObject: value),
          let raw = String(data: data, encoding: .utf8) else { return }
    defaults.set(raw, forKey: key)
    defaults.synchronize()
  }

  func remove(_ key: String) {
    defaults.removeObject(forKey: key)
    defaults.synchronize()
  }
}

final class KeyboardViewController: UIInputViewController {
  private let statusLabel = UILabel()
  private let micButton = UIButton(type: .system)
  private let globeButton = UIButton(type: .system)
  private var observingDarwin = false

  // MARK: - 생명주기
  // 결과 삽입은 여러 곳에서 시도한다(나타남·입력란 변경·Darwin 알림). consumed 표시로 한 번만 들어간다.

  override func viewDidLoad() {
    super.viewDidLoad()
    buildUI()
  }

  override func viewWillAppear(_ animated: Bool) {
    super.viewWillAppear(animated)
    startObservingResult()
    refreshStatus()
  }

  override func viewDidAppear(_ animated: Bool) {
    super.viewDidAppear(animated)
    // 입력란(textDocumentProxy) 연결은 나타난 뒤가 안전하다.
    deliverResultIfReady()
  }

  override func viewDidDisappear(_ animated: Bool) {
    super.viewDidDisappear(animated)
    stopObservingResult()
  }

  override func viewWillLayoutSubviews() {
    super.viewWillLayoutSubviews()
    globeButton.isHidden = !needsInputModeSwitchKey
  }

  override func textDidChange(_ textInput: UITextInput?) {
    super.textDidChange(textInput)
    deliverResultIfReady()
  }

  deinit {
    stopObservingResult()
  }

  // MARK: - UI

  private func buildUI() {
    guard let root = inputView else { return }
    root.allowsSelfSizing = true

    statusLabel.font = .preferredFont(forTextStyle: .footnote)
    statusLabel.textColor = .secondaryLabel
    statusLabel.textAlignment = .center
    statusLabel.numberOfLines = 2
    statusLabel.accessibilityIdentifier = "murdic.status"

    var micConfig = UIButton.Configuration.filled()
    micConfig.image = UIImage(systemName: "mic.fill")
    micConfig.title = "말하기"
    micConfig.imagePadding = 8
    micConfig.cornerStyle = .capsule
    micConfig.baseBackgroundColor = UIColor(red: 0.07, green: 0.47, blue: 0.47, alpha: 1)
    micButton.configuration = micConfig
    micButton.accessibilityIdentifier = "murdic.mic"
    micButton.addTarget(self, action: #selector(micTapped), for: .touchUpInside)

    globeButton.setImage(UIImage(systemName: "globe"), for: .normal)
    globeButton.accessibilityLabel = "다음 키보드"
    globeButton.addTarget(self, action: #selector(handleInputModeList(from:with:)), for: .allTouchEvents)

    let space = keyButton(title: "스페이스", id: "murdic.space") { [weak self] in
      self?.textDocumentProxy.insertText(" ")
    }
    let delete = keyButton(systemImage: "delete.left", id: "murdic.delete") { [weak self] in
      self?.textDocumentProxy.deleteBackward()
    }
    let ret = keyButton(systemImage: "return", id: "murdic.return") { [weak self] in
      self?.textDocumentProxy.insertText("\n")
    }

    let bottom = UIStackView(arrangedSubviews: [globeButton, space, delete, ret])
    bottom.axis = .horizontal
    bottom.spacing = 6
    bottom.distribution = .fill
    space.setContentHuggingPriority(.defaultLow, for: .horizontal)
    for b in [globeButton, delete, ret] {
      b.widthAnchor.constraint(equalToConstant: 52).isActive = true
      b.setContentHuggingPriority(.required, for: .horizontal)
    }

    let column = UIStackView(arrangedSubviews: [statusLabel, micButton, bottom])
    column.axis = .vertical
    column.spacing = 10
    column.translatesAutoresizingMaskIntoConstraints = false
    root.addSubview(column)

    NSLayoutConstraint.activate([
      column.leadingAnchor.constraint(equalTo: root.leadingAnchor, constant: 8),
      column.trailingAnchor.constraint(equalTo: root.trailingAnchor, constant: -8),
      column.topAnchor.constraint(equalTo: root.topAnchor, constant: 8),
      column.bottomAnchor.constraint(equalTo: root.bottomAnchor, constant: -8),
      micButton.heightAnchor.constraint(equalToConstant: 96),
      bottom.heightAnchor.constraint(equalToConstant: 44),
    ])
  }

  private func keyButton(title: String? = nil, systemImage: String? = nil, id: String,
                         action: @escaping () -> Void) -> UIButton {
    var config = UIButton.Configuration.gray()
    config.title = title
    if let systemImage { config.image = UIImage(systemName: systemImage) }
    config.cornerStyle = .medium
    let button = UIButton(configuration: config, primaryAction: UIAction { _ in action() })
    button.accessibilityIdentifier = id
    return button
  }

  private func setStatus(_ text: String) {
    statusLabel.text = text
  }

  private func refreshStatus() {
    if !hasFullAccess {
      setStatus("전체 접근을 켜 주세요: 설정 › 일반 › 키보드 › 키보드 › 머딕")
    } else {
      setStatus("🎤를 누르면 머딕 앱이 열립니다. 말한 뒤 돌아오면 입력돼요.")
    }
  }

  // MARK: - 🎤 → 앱 열기

  @objc private func micTapped() {
    guard hasFullAccess, let store = SharedStore() else {
      setStatus("전체 접근이 꺼져 있어 앱과 결과를 주고받을 수 없어요. 설정 › 일반 › 키보드 › 키보드 › 머딕")
      return
    }
    let req = UUID().uuidString
    store.write(SharedConfig.pendingKey, ["req": req, "createdAt": nowMs()])

    var comps = URLComponents()
    comps.scheme = "murdic"
    comps.host = "dictate"
    comps.queryItems = [URLQueryItem(name: "req", value: req), URLQueryItem(name: "src", value: "keyboard")]
    guard let url = comps.url else { return }

    if openContainingApp(url) {
      setStatus("머딕 앱에서 말한 뒤 이 앱으로 돌아오세요.")
    } else {
      setStatus("머딕 앱을 직접 열어 말한 뒤 돌아오세요.")
    }
  }

  /// 키보드에서는 extensionContext.open이 동작하지 않는다. 응답자 체인에서 UIApplication을 찾아
  /// openURL:options:completionHandler:를 직접 부른다. 공개 API 우회 방식(docs/ios-keyboard.md 3.1).
  private func openContainingApp(_ url: URL) -> Bool {
    let selector = sel_registerName("openURL:options:completionHandler:")
    var responder: UIResponder? = self
    while let r = responder {
      if r.responds(to: selector), r.isKind(of: NSClassFromString("UIApplication") ?? NSNull.self) {
        typealias OpenURL = @convention(c) (AnyObject, Selector, NSURL, NSDictionary,
                                            (@convention(block) (Bool) -> Void)?) -> Void
        let imp = r.method(for: selector)
        let open = unsafeBitCast(imp, to: OpenURL.self)
        open(r, selector, url as NSURL, NSDictionary(), nil)
        return true
      }
      responder = r.next
    }
    return false
  }

  // MARK: - 결과 받기 → 입력

  private func deliverResultIfReady() {
    guard hasFullAccess, let store = SharedStore(),
          let pending = store.read(SharedConfig.pendingKey),
          let result = store.read(SharedConfig.resultKey),
          let req = pending["req"] as? String,
          result["req"] as? String == req,
          (result["consumed"] as? Bool) != true,
          let text = result["text"] as? String,
          let finishedAt = result["finishedAt"] as? Double else { return }

    guard nowMs() - finishedAt < SharedConfig.resultMaxAgeMs else {
      store.remove(SharedConfig.pendingKey)
      return
    }
    textDocumentProxy.insertText(text)
    // 넣은 뒤 본문은 지우고 consumed만 남긴다(같은 결과 두 번 입력 방지).
    store.write(SharedConfig.resultKey, ["req": req, "text": "", "finishedAt": finishedAt, "consumed": true])
    store.remove(SharedConfig.pendingKey)
    setStatus("입력했습니다 ✓")
  }

  private func startObservingResult() {
    guard !observingDarwin else { return }
    observingDarwin = true
    let center = CFNotificationCenterGetDarwinNotifyCenter()
    let observer = Unmanaged.passUnretained(self).toOpaque()
    CFNotificationCenterAddObserver(center, observer, { _, observer, _, _, _ in
      guard let observer else { return }
      let vc = Unmanaged<KeyboardViewController>.fromOpaque(observer).takeUnretainedValue()
      DispatchQueue.main.async { vc.deliverResultIfReady() }
    }, SharedConfig.resultDarwinName as CFString, nil, .deliverImmediately)
  }

  private func stopObservingResult() {
    guard observingDarwin else { return }
    observingDarwin = false
    let observer = Unmanaged.passUnretained(self).toOpaque()
    CFNotificationCenterRemoveObserver(CFNotificationCenterGetDarwinNotifyCenter(), observer,
                                       CFNotificationName(SharedConfig.resultDarwinName as CFString), nil)
  }
}
