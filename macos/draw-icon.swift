import AppKit
let S: CGFloat = 1024
let img = NSImage(size: NSSize(width: S, height: S))
img.lockFocus()
func rgb(_ h: Int, _ a: CGFloat = 1) -> NSColor {
  NSColor(srgbRed: CGFloat((h>>16)&255)/255, green: CGFloat((h>>8)&255)/255, blue: CGFloat(h&255)/255, alpha: a)
}
// macOS icon grid: 824pt rounded square centred in 1024
let r = NSRect(x: 100, y: 100, width: 824, height: 824)
let bg = NSBezierPath(roundedRect: r, xRadius: 185, yRadius: 185)
NSGradient(starting: rgb(0x27272a), ending: rgb(0x09090b))!.draw(in: bg, angle: -90)
rgb(0x3f3f46).setStroke(); bg.lineWidth = 4; bg.stroke()
// node graph
let n: [CGPoint] = [CGPoint(x:330,y:650), CGPoint(x:560,y:720), CGPoint(x:700,y:520),
                    CGPoint(x:470,y:470), CGPoint(x:320,y:330), CGPoint(x:600,y:300)]
let edges = [(0,1),(1,2),(0,3),(1,3),(2,3),(3,4),(3,5),(2,5)]
rgb(0x71717a).setStroke()
for (a,b) in edges { let p = NSBezierPath(); p.move(to:n[a]); p.line(to:n[b]); p.lineWidth = 14; p.lineCapStyle = .round; p.stroke() }
func dot(_ p: CGPoint, _ rad: CGFloat, _ c: NSColor) { c.setFill(); NSBezierPath(ovalIn: NSRect(x:p.x-rad,y:p.y-rad,width:rad*2,height:rad*2)).fill() }
for (i,p) in n.enumerated() where i != 3 { dot(p, i == 2 ? 0 : 44, rgb(0xe4e4e7)) }
// live node: green with a halo, as in the app's graph
dot(n[2], 92, rgb(0x22c55e, 0.22)); dot(n[2], 52, rgb(0x22c55e))
dot(n[3], 58, rgb(0xffffff))
img.unlockFocus()
let png = NSBitmapImageRep(data: img.tiffRepresentation!)!.representation(using: .png, properties: [:])!
try! png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
