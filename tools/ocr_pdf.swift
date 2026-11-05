// Local OCR for image-only PDFs using Apple's Vision framework (no network, nothing to install).
// Usage: swift ocr_pdf.swift <in.pdf> <out.txt> [firstPage lastPage]   (pages are 1-based)
import Foundation
import PDFKit
import Vision

let args = CommandLine.arguments
guard args.count >= 3, let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    FileHandle.standardError.write("usage: ocr_pdf.swift in.pdf out.txt [first last]\n".data(using: .utf8)!)
    exit(2)
}
let first = args.count >= 5 ? max(1, Int(args[3]) ?? 1) : 1
let last = args.count >= 5 ? min(doc.pageCount, Int(args[4]) ?? doc.pageCount) : doc.pageCount
var out = ""
var lowConf = 0

func render(_ page: PDFPage, scale: CGFloat) -> CGImage? {
    let b = page.bounds(for: .mediaBox)
    let w = Int(b.width * scale), h = Int(b.height * scale)
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    page.draw(with: .mediaBox, to: ctx)
    return ctx.makeImage()
}

for p in first...last {
    guard let page = doc.page(at: p - 1) else { continue }
    // aim for ~2400px on the long side: readable small print without huge memory
    let b = page.bounds(for: .mediaBox)
    let scale = min(4.0, 2400.0 / max(b.width, b.height))
    guard let img = render(page, scale: scale) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    try? VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
    let obs = (req.results ?? []).sorted {
        // top-to-bottom, then left-to-right (Vision's origin is bottom-left)
        abs($0.boundingBox.midY - $1.boundingBox.midY) > 0.01 ? $0.boundingBox.midY > $1.boundingBox.midY
                                                              : $0.boundingBox.minX < $1.boundingBox.minX
    }
    var lines: [String] = []
    for o in obs {
        guard let c = o.topCandidates(1).first else { continue }
        if c.confidence < 0.4 { lowConf += 1; continue }
        lines.append(c.string)
    }
    out += "[Page \(p)]\n" + lines.joined(separator: "\n") + "\n\n"
    FileHandle.standardError.write("page \(p)/\(last): \(lines.count) lines\n".data(using: .utf8)!)
}
try? out.write(toFile: args[2], atomically: true, encoding: .utf8)
FileHandle.standardError.write("done. dropped \(lowConf) low-confidence lines\n".data(using: .utf8)!)
