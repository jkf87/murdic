// MurdicShared — 키보드 익스텐션과 App Group으로 받아쓰기 결과를 주고받는 iOS 전용 모듈.
// 설계: docs/ios-keyboard.md 3절. 키 이름·App Group ID는 MurdicKeyboard/KeyboardViewController.swift와 같아야 한다.
//
// JS:
//   NativeModules.MurdicShared.writeResult(req: string, text: string): Promise<void>
//   NativeModules.MurdicShared.readPending(): Promise<{req: string, createdAt: number /* ms */} | null>

#import <React/RCTBridgeModule.h>
#import <Foundation/Foundation.h>

static NSString *const kMurdicAppGroup = @"group.com.murdic.mobile";
static NSString *const kPendingKey = @"murdic.pending";
static NSString *const kResultKey = @"murdic.result";
static NSString *const kResultDarwinName = @"com.murdic.mobile.result";
static const double kPendingMaxMs = 5 * 60 * 1000;

@interface MurdicShared : NSObject <RCTBridgeModule>
@end

@implementation MurdicShared

RCT_EXPORT_MODULE();

+ (BOOL)requiresMainQueueSetup
{
  return NO;
}

static NSUserDefaults *MurdicDefaults(void)
{
  return [[NSUserDefaults alloc] initWithSuiteName:kMurdicAppGroup];
}

static double NowMs(void)
{
  return [[NSDate date] timeIntervalSince1970] * 1000.0;
}

static NSDictionary *ReadJSON(NSUserDefaults *defaults, NSString *key)
{
  NSString *raw = [defaults stringForKey:key];
  if (raw.length == 0) {
    return nil;
  }
  NSData *data = [raw dataUsingEncoding:NSUTF8StringEncoding];
  id obj = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
  return [obj isKindOfClass:[NSDictionary class]] ? obj : nil;
}

RCT_EXPORT_METHOD(writeResult : (NSString *)req
                  text : (NSString *)text
                  resolver : (RCTPromiseResolveBlock)resolve
                  rejecter : (RCTPromiseRejectBlock)reject)
{
  NSUserDefaults *defaults = MurdicDefaults();
  if (defaults == nil) {
    reject(@"no_app_group", @"App Group을 열 수 없습니다(entitlements 확인)", nil);
    return;
  }
  NSDictionary *result = @{
    @"req" : req ?: @"",
    @"text" : text ?: @"",
    @"finishedAt" : @(NowMs()),
    @"consumed" : @NO,
  };
  NSError *error = nil;
  NSData *data = [NSJSONSerialization dataWithJSONObject:result options:0 error:&error];
  if (data == nil) {
    reject(@"encode_failed", error.localizedDescription, error);
    return;
  }
  [defaults setObject:[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding] forKey:kResultKey];
  [defaults synchronize];

  // 떠 있는 키보드에게 "결과 왔음"을 알린다(내용은 싣지 않는다).
  CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(),
                                       (__bridge CFStringRef)kResultDarwinName, NULL, NULL, true);
  resolve(nil);
}

RCT_EXPORT_METHOD(readPending : (RCTPromiseResolveBlock)resolve rejecter : (RCTPromiseRejectBlock)reject)
{
  NSUserDefaults *defaults = MurdicDefaults();
  NSDictionary *pending = defaults ? ReadJSON(defaults, kPendingKey) : nil;
  NSString *req = pending[@"req"];
  NSNumber *createdAt = pending[@"createdAt"];
  if (![req isKindOfClass:[NSString class]] || ![createdAt isKindOfClass:[NSNumber class]]) {
    resolve([NSNull null]);
    return;
  }
  // 이미 결과를 보낸 요청이면 다시 이어받지 않는다.
  NSDictionary *result = ReadJSON(defaults, kResultKey);
  if ([result[@"req"] isEqual:req]) {
    resolve([NSNull null]);
    return;
  }
  if (NowMs() - createdAt.doubleValue > kPendingMaxMs) {
    resolve([NSNull null]);
    return;
  }
  resolve(@{@"req" : req, @"createdAt" : createdAt});
}

@end
