import CoreGraphics
import Foundation
import MonetProtocol
import MonetRender

/// `monet-render` — the Swift parity lane for `scripts/render-study.py`
/// (performer-render spec §15.3). Reads a `RenderStudyDocument` (the same
/// `--json` shape the Python tooling already produces/consumes) from a file
/// argument or stdin, renders it with `CoreGraphicsCanvasRenderer`, and
/// writes a PNG at the document's exact `width x height` (no DPI scaling) to
/// the given output path or stdout.
///
/// Usage: monet-render <input.json> <output.png>
///        monet-render --stdin <output.png>   (reads JSON from stdin)
struct MonetRenderCLI {
    static func run(arguments: [String]) -> Int32 {
        guard arguments.count >= 2 else {
            FileHandle.standardError.write(Data("usage: monet-render <input.json|--stdin> <output.png>\n".utf8))
            return 64
        }
        let inputArg = arguments[0]
        let outputPath = arguments[1]

        let data: Data
        do {
            data = inputArg == "--stdin"
                ? FileHandle.standardInput.readDataToEndOfFile()
                : try Data(contentsOf: URL(fileURLWithPath: inputArg))
        } catch {
            FileHandle.standardError.write(Data("failed to read input: \(error)\n".utf8))
            return 1
        }

        let document: RenderStudyDocument
        do {
            document = try JSONDecoder().decode(RenderStudyDocument.self, from: data)
        } catch {
            FileHandle.standardError.write(Data("failed to decode RenderStudyDocument: \(error)\n".utf8))
            return 1
        }

        let styleConfig: DrawingStyleConfig = document.style == .paint ? .paint : .plotter
        let renderer = CoreGraphicsCanvasRenderer()
        guard let image = renderer.renderCommitted(
            strokes: document.paths,
            styleConfig: styleConfig,
            size: CGSize(width: document.width, height: document.height)
        ) else {
            FileHandle.standardError.write(Data("render failed\n".utf8))
            return 1
        }

        do {
            try PNGWriter.write(image, to: URL(fileURLWithPath: outputPath))
        } catch {
            FileHandle.standardError.write(Data("failed to write PNG: \(error)\n".utf8))
            return 1
        }
        return 0
    }
}

exit(MonetRenderCLI.run(arguments: Array(CommandLine.arguments.dropFirst())))
