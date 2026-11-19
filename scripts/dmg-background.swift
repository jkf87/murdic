// Draws the DMG window background (640 x 400 points) used by scripts/build-release.py.
// Usage: dmg-background <output.png>
import AppKit

let width = 640, height = 400
guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height,
                                 bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                 colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
      let context = NSGraphicsContext(bitmapImageRep: rep) else {
    fatalError("cannot create bitmap")
}
NSGraphicsContext.current = context
let canvas = NSRect(x: 0, y: 0, width: width, height: height)
NSGradient(starting: NSColor(calibratedWhite: 0.98, alpha: 1), ending: NSColor(calibratedWhite: 0.90, alpha: 1))?
    .draw(in: canvas, angle: 270)

// Arrow from the app icon (left) to the Applications alias (right); icons sit at y = 190 in Finder coordinates.
let arrow = NSBezierPath()
arrow.move(to: NSPoint(x: 262, y: 228))
arrow.line(to: NSPoint(x: 362, y: 228))
arrow.line(to: NSPoint(x: 362, y: 246))
arrow.line(to: NSPoint(x: 398, y: 212))
arrow.line(to: NSPoint(x: 362, y: 178))
arrow.line(to: NSPoint(x: 362, y: 196))
arrow.line(to: NSPoint(x: 262, y: 196))
arrow.close()
NSColor(calibratedWhite: 0.55, alpha: 1).setFill()
arrow.fill()

let caption = "murdic을 Applications 폴더로 끌어 놓으세요"
let attributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 15, weight: .medium),
    .foregroundColor: NSColor(calibratedWhite: 0.25, alpha: 1),
]
let size = (caption as NSString).size(withAttributes: attributes)
(caption as NSString).draw(at: NSPoint(x: (CGFloat(width) - size.width) / 2, y: 52), withAttributes: attributes)

NSGraphicsContext.current = nil
guard let png = rep.representation(using: .png, properties: [:]) else { fatalError("cannot encode PNG") }
try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
