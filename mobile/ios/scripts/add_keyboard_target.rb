# Murdic.xcodeproj에 iOS 전용 구성을 넣는다(여러 번 돌려도 같은 결과).
#  - 앱: MurdicShared.m 소스, Murdic.entitlements(App Group)
#  - MurdicKeyboard 키보드 익스텐션 타깃 + 앱에 Embed App Extensions
#
# 실행: mobile/ios 에서  ./scripts/xcodeproj-ruby scripts/add_keyboard_target.rb
# (Homebrew CocoaPods에 들어 있는 xcodeproj gem을 쓴다. Xcode 없이도 돈다.)

require 'xcodeproj'

IOS_DIR = File.expand_path('..', __dir__)
PROJECT_PATH = File.join(IOS_DIR, 'Murdic.xcodeproj')
APP_BUNDLE_ID = 'com.murdic.mobile'
KB_NAME = 'MurdicKeyboard'
KB_BUNDLE_ID = "#{APP_BUNDLE_ID}.keyboard"
DEPLOYMENT_TARGET = '15.1'

project = Xcodeproj::Project.open(PROJECT_PATH)
app = project.targets.find { |t| t.name == 'Murdic' } or abort('Murdic 타깃이 없습니다')
app_group = project.main_group.find_subpath('Murdic', false) or abort('Murdic 그룹이 없습니다')

def file_ref(group, path)
  group.files.find { |f| f.path == path } || group.new_reference(path)
end

# --- 앱 타깃 ---------------------------------------------------------------
shared_ref = file_ref(app_group, 'MurdicShared.m')
app.source_build_phase.add_file_reference(shared_ref, true)
file_ref(app_group, 'Murdic.entitlements')
app.build_configurations.each do |c|
  c.build_settings['CODE_SIGN_ENTITLEMENTS'] = 'Murdic/Murdic.entitlements'
end

# --- 키보드 익스텐션 타깃 ---------------------------------------------------
kb = project.targets.find { |t| t.name == KB_NAME }
unless kb
  kb = project.new_target(:app_extension, KB_NAME, :ios, DEPLOYMENT_TARGET, nil, :swift)
  puts "타깃 생성: #{KB_NAME}"
end

kb_group = project.main_group.find_subpath(KB_NAME, false) ||
           project.main_group.new_group(KB_NAME, KB_NAME)
swift_ref = file_ref(kb_group, 'KeyboardViewController.swift')
kb.source_build_phase.add_file_reference(swift_ref, true)
file_ref(kb_group, 'Info.plist')
file_ref(kb_group, "#{KB_NAME}.entitlements")

kb.build_configurations.each do |c|
  s = c.build_settings
  s['PRODUCT_NAME'] = '$(TARGET_NAME)'
  s['PRODUCT_BUNDLE_IDENTIFIER'] = KB_BUNDLE_ID
  s['INFOPLIST_FILE'] = "#{KB_NAME}/Info.plist"
  s['GENERATE_INFOPLIST_FILE'] = 'NO'
  s['CODE_SIGN_ENTITLEMENTS'] = "#{KB_NAME}/#{KB_NAME}.entitlements"
  s['SWIFT_VERSION'] = '5.0'
  s['IPHONEOS_DEPLOYMENT_TARGET'] = DEPLOYMENT_TARGET
  s['TARGETED_DEVICE_FAMILY'] = '1,2'
  s['APPLICATION_EXTENSION_API_ONLY'] = 'YES'
  s['SKIP_INSTALL'] = 'YES'
  s['MARKETING_VERSION'] = '1.0'
  s['CURRENT_PROJECT_VERSION'] = '1'
  s['LD_RUNPATH_SEARCH_PATHS'] = ['$(inherited)', '@executable_path/Frameworks', '@executable_path/../../Frameworks']
  s['ENABLE_USER_SCRIPT_SANDBOXING'] = 'NO'
  s['CODE_SIGN_STYLE'] = 'Automatic'
  # 앱 타깃과 같은 팀으로 서명(사람이 Xcode에서 Team을 고르면 둘 다 바뀐다).
  team = app.build_configurations.first.build_settings['DEVELOPMENT_TEAM']
  s['DEVELOPMENT_TEAM'] = team if team
end

# --- 앱이 키보드를 만들고 품게 하기 -------------------------------------------
app.add_dependency(kb) unless app.dependencies.any? { |d| d.target == kb }

embed = app.copy_files_build_phases.find { |p| p.name == 'Embed App Extensions' }
unless embed
  embed = project.new(Xcodeproj::Project::Object::PBXCopyFilesBuildPhase)
  embed.name = 'Embed App Extensions'
  embed.symbol_dst_subfolder_spec = :plug_ins
  # RN의 "Bundle React Native code and images" 스크립트보다 앞에 두어야 빌드 순환(Cycle) 오류가 나지 않는다.
  resources_index = app.build_phases.index(app.resources_build_phase) || (app.build_phases.size - 1)
  app.build_phases.insert(resources_index + 1, embed)
end
unless embed.files_references.include?(kb.product_reference)
  bf = embed.add_file_reference(kb.product_reference, true)
  bf.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }
end

project.save
puts '완료: ' + project.targets.map(&:name).join(', ')
puts '앱 빌드 단계: ' + app.build_phases.map { |p| p.display_name }.join(' → ')
