import CoreAudio
import Foundation

struct Microphone: Equatable {
    let id: AudioDeviceID
    let uid: String
    let name: String
}

struct InputDevices: Equatable {
    var devices: [Microphone] = []
    var defaultID: AudioDeviceID = kAudioObjectUnknown
    var systemDefault: Microphone? { devices.first { $0.id == defaultID } }

    static func enumerate() -> InputDevices? {
        let system = AudioObjectID(kAudioObjectSystemObject)
        var address = property(kAudioHardwarePropertyDevices)
        var bytes: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(system, &address, 0, nil, &bytes) == noErr else { return nil }
        var ids = [AudioDeviceID](repeating: 0, count: Int(bytes) / MemoryLayout<AudioDeviceID>.size)
        if !ids.isEmpty {
            let status = ids.withUnsafeMutableBytes {
                AudioObjectGetPropertyData(system, &address, 0, nil, &bytes, $0.baseAddress!)
            }
            guard status == noErr else { return nil }
        }
        let devices = ids.prefix(Int(bytes) / MemoryLayout<AudioDeviceID>.size).compactMap { id -> Microphone? in
            guard hasInput(id), let uid = string(id, kAudioDevicePropertyDeviceUID),
                  let name = string(id, kAudioObjectPropertyName) else { return nil }
            return Microphone(id: id, uid: uid, name: name)
        }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
        var defaultID = AudioDeviceID(kAudioObjectUnknown)
        address = property(kAudioHardwarePropertyDefaultInputDevice)
        bytes = UInt32(MemoryLayout.size(ofValue: defaultID))
        _ = AudioObjectGetPropertyData(system, &address, 0, nil, &bytes, &defaultID)
        return InputDevices(devices: devices, defaultID: defaultID)
    }

    static func property(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
        AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                                   mElement: kAudioObjectPropertyElementMain)
    }

    private static func hasInput(_ id: AudioDeviceID) -> Bool {
        var address = property(kAudioDevicePropertyStreamConfiguration)
        address.mScope = kAudioDevicePropertyScopeInput
        var bytes: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(id, &address, 0, nil, &bytes) == noErr,
              bytes >= MemoryLayout<AudioBufferList>.size else { return false }
        let raw = UnsafeMutableRawPointer.allocate(byteCount: Int(bytes), alignment: MemoryLayout<AudioBufferList>.alignment)
        defer { raw.deallocate() }
        guard AudioObjectGetPropertyData(id, &address, 0, nil, &bytes, raw) == noErr else { return false }
        return UnsafeMutableAudioBufferListPointer(raw.assumingMemoryBound(to: AudioBufferList.self))
            .contains { $0.mNumberChannels > 0 }
    }

    private static func string(_ id: AudioDeviceID, _ selector: AudioObjectPropertySelector) -> String? {
        var address = property(selector)
        var value: Unmanaged<CFString>?
        var bytes = UInt32(MemoryLayout.size(ofValue: value))
        guard AudioObjectGetPropertyData(id, &address, 0, nil, &bytes, &value) == noErr else { return nil }
        return value?.takeRetainedValue() as String?
    }
}

// A missing pinned UID is cleared once, including across restarts. Reconnecting
// a flaky USB device must not take ownership of the microphone again.
final class MicrophoneSelection {
    private let defaults: UserDefaults
    private(set) var inputs = InputDevices()
    private(set) var pinnedUID: String?
    var active: Microphone? {
        if let pinnedUID { return inputs.devices.first { $0.uid == pinnedUID } }
        return inputs.systemDefault
    }
    var defaultTitle: String { "시스템 기본값 (현재: \(inputs.systemDefault?.name ?? "없음"))" }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        pinnedUID = defaults.string(forKey: "microphoneUID")
    }

    func select(_ mic: Microphone?) {
        pinnedUID = mic?.uid
        defaults.set(mic?.uid, forKey: "microphoneUID")
        defaults.set(mic?.name, forKey: "microphoneName")
    }

    func update(_ snapshot: InputDevices) -> String? {
        inputs = snapshot
        guard let uid = pinnedUID, !inputs.devices.contains(where: { $0.uid == uid }) else { return nil }
        let lost = defaults.string(forKey: "microphoneName") ?? "선택한 마이크"
        select(nil)
        return lost
    }
}

final class InputDeviceObserver {
    private let listener: AudioObjectPropertyListenerBlock
    private var watched: [AudioObjectPropertyAddress] = []

    init(changed: @escaping () -> Void) {
        listener = { _, _ in changed() }
        for selector in [kAudioHardwarePropertyDevices, kAudioHardwarePropertyDefaultInputDevice] {
            var address = InputDevices.property(selector)
            if AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address,
                                                   .main, listener) == noErr { watched.append(address) }
        }
    }

    deinit {
        for var address in watched {
            AudioObjectRemovePropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address, .main, listener)
        }
    }
}
