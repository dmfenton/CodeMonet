import Foundation
@testable import MonetProtocol
import Testing

/// Decode coverage for the program-painting wire additions: the
/// `painting_version` server message, `init.painting`, `reveal.json`
/// (`RevealManifest`/`RevealKeyframe`/`RevealOp`), and the raster gallery
/// fields (program-painting spec §1-3, §5).
@Suite("Program painting decoding")
struct PaintingVersionDecodingTests {
    @Test("decodes painting_version with all required fields")
    func decodesPaintingVersion() throws {
        let json = Data(#"""
        {
          "type": "painting_version",
          "piece_number": 12,
          "version": 3,
          "asset_base": "/painting-assets/u/tok/",
          "image_width": 1600,
          "image_height": 1200,
          "stages": ["ground", "sky", "sky", "sky", "boat"]
        }
        """#.utf8)
        let message = try JSONDecoder().decode(ServerMessage.self, from: json)
        guard case let .paintingVersion(ref, stages, ops) = message else {
            Issue.record("expected .paintingVersion")
            return
        }
        #expect(ref.pieceNumber == 12)
        #expect(ref.version == 3)
        #expect(ref.assetBase == "/painting-assets/u/tok/")
        #expect(ref.imageWidth == 1600)
        #expect(ref.imageHeight == 1200)
        // Server dedupes only *consecutive* duplicates before sending; the
        // client must not attempt to re-dedupe non-consecutive repeats.
        #expect(stages == ["ground", "sky", "sky", "sky", "boat"])
        // `ops` is an additive server field: absent here, so nil.
        #expect(ops == nil)
    }

    static let styleConfigJSON = """
        {"type":"paint","name":"Paint","description":"d",
         "agent_stroke":{"color":"#000","stroke_width":8,"opacity":0.85,"stroke_linecap":"round","stroke_linejoin":"round"},
         "human_stroke":{"color":"#000","stroke_width":8,"opacity":0.85,"stroke_linecap":"round","stroke_linejoin":"round"},
         "supports_color":true,"supports_variable_width":true,"supports_opacity":true,"color_palette":null}
        """

    @Test("init decodes a present painting ref (no stages field)")
    func initDecodesPaintingRef() throws {
        let json = Data("""
        {
          "type": "init",
          "strokes": [], "gallery": [], "status": "idle", "paused": true,
          "piece_number": 12, "canvas_width": 800, "canvas_height": 600,
          "monologue": "", "drawing_style": "paint", "style_config": \(Self.styleConfigJSON),
          "painting": {
            "piece_number": 12, "version": 3,
            "asset_base": "/painting-assets/u/tok/",
            "image_width": 1600, "image_height": 1200
          }
        }
        """.utf8)
        let message = try JSONDecoder().decode(ServerMessage.self, from: json)
        guard case let .initial(payload) = message else {
            Issue.record("expected .initial")
            return
        }
        #expect(payload.painting?.pieceNumber == 12)
        #expect(payload.painting?.version == 3)
        #expect(payload.painting?.assetBase == "/painting-assets/u/tok/")
    }

    @Test("init tolerates an absent painting field (older recording, or no current painting)")
    func initToleratesMissingPainting() throws {
        let json = Data("""
        {
          "type": "init",
          "strokes": [], "gallery": [], "status": "idle", "paused": true,
          "piece_number": 1, "canvas_width": 800, "canvas_height": 600,
          "monologue": "", "drawing_style": "paint", "style_config": \(Self.styleConfigJSON)
        }
        """.utf8)
        let message = try JSONDecoder().decode(ServerMessage.self, from: json)
        guard case let .initial(payload) = message else {
            Issue.record("expected .initial")
            return
        }
        #expect(payload.painting == nil)
    }

    @Test("init tolerates an explicit painting: null")
    func initToleratesNullPainting() throws {
        let json = Data("""
        {
          "type": "init",
          "strokes": [], "gallery": [], "status": "idle", "paused": true,
          "piece_number": 1, "canvas_width": 800, "canvas_height": 600,
          "monologue": "", "drawing_style": "paint", "style_config": \(Self.styleConfigJSON),
          "painting": null
        }
        """.utf8)
        let message = try JSONDecoder().decode(ServerMessage.self, from: json)
        guard case let .initial(payload) = message else {
            Issue.record("expected .initial")
            return
        }
        #expect(payload.painting == nil)
    }

    @Test("decodes a full reveal.json manifest, including a single-point (dot) stroke op")
    func decodesRevealManifest() throws {
        // Trimmed real-shaped fixture (program-painting spec §3.3), plus a
        // single-point stroke op appended to `sky` to cover the dot case.
        let json = Data(#"""
        {
          "width": 1600,
          "height": 1200,
          "keyframes": [
            { "label": "ground", "image": "kf_00.jpg", "ops": [["a", 0, 0, 1600, 1200]] },
            {
              "label": "sky",
              "image": "kf_01.jpg",
              "ops": [
                ["a", 0, 0, 1600, 701],
                ["s", 18.2, 648.2, 94.0, 669.3, 88.5, 683.5, 85.1],
                ["s", 8, 50, 60]
              ]
            }
          ]
        }
        """#.utf8)
        let manifest = try JSONDecoder().decode(RevealManifest.self, from: json)
        #expect(manifest.width == 1600)
        #expect(manifest.height == 1200)
        #expect(manifest.keyframes.count == 2)
        guard case let .area(x0, y0, x1, y1) = manifest.keyframes[0].ops[0] else {
            Issue.record("expected area op")
            return
        }
        #expect((x0, y0, x1, y1) == (0, 0, 1600, 1200))

        guard case let .stroke(width, points) = manifest.keyframes[1].ops[1] else {
            Issue.record("expected stroke op")
            return
        }
        #expect(width == 18.2)
        #expect(points.count == 3)
        #expect(points.first == Point(x: 648.2, y: 94.0))

        // Single-point stroke: a dot, not a degenerate line.
        guard case let .stroke(dotWidth, dotPoints) = manifest.keyframes[1].ops[2] else {
            Issue.record("expected single-point stroke op")
            return
        }
        #expect(dotWidth == 8)
        #expect(dotPoints == [Point(x: 50, y: 60)])
    }

    @Test("area op normalizes so x0<x1, y0<y1 regardless of input order")
    func areaOpNormalizes() throws {
        let json = Data(#"["a", 1600, 1200, 0, 0]"#.utf8)
        let op = try JSONDecoder().decode(RevealOp.self, from: json)
        guard case let .area(x0, y0, x1, y1) = op else {
            Issue.record("expected area op")
            return
        }
        #expect((x0, y0, x1, y1) == (0, 0, 1600, 1200))
    }

    @Test("malformed stroke op (even numeric count after width) throws rather than silently truncating")
    func malformedStrokeOpThrows() {
        let json = Data(#"["s", 8, 1, 2, 3]"#.utf8)
        #expect(throws: RevealOpDecodingError.self) {
            _ = try JSONDecoder().decode(RevealOp.self, from: json)
        }
    }

    @Test("stroke op with width <= 0 throws, mirroring parseRevealOp's rejection")
    func nonPositiveWidthStrokeOpThrows() {
        let json = Data(#"["s", 0, 1, 2, 3, 4]"#.utf8)
        #expect(throws: RevealOpDecodingError.self) {
            _ = try JSONDecoder().decode(RevealOp.self, from: json)
        }
    }

    @Test("gallery entry defaults format to strokes when absent")
    func galleryEntryDefaultsFormat() throws {
        let json = Data(#"{"id":"p1","created_at":"2026-01-01T00:00:00Z","piece_number":1,"stroke_count":3}"#.utf8)
        let entry = try JSONDecoder().decode(GalleryEntry.self, from: json)
        #expect(entry.format == .strokes)
    }

    @Test("gallery entry decodes an explicit raster format")
    func galleryEntryDecodesRasterFormat() throws {
        let json = Data(#"{"id":"p1","created_at":"2026-01-01T00:00:00Z","piece_number":1,"stroke_count":0,"format":"raster"}"#.utf8)
        let entry = try JSONDecoder().decode(GalleryEntry.self, from: json)
        #expect(entry.format == .raster)
    }

    @Test("GET /gallery/{n}/strokes decodes format + image_url for a raster piece")
    func galleryPieceStrokesDecodesRaster() throws {
        let json = Data(#"""
        {
          "strokes": [], "piece_number": 12, "canvas_width": 1600, "canvas_height": 1200,
          "drawing_style": "paint", "format": "raster",
          "image_url": "/painting-assets/u/tok/final.png"
        }
        """#.utf8)
        let piece = try JSONDecoder().decode(GalleryPieceStrokes.self, from: json)
        #expect(piece.format == .raster)
        #expect(piece.imageURL == "/painting-assets/u/tok/final.png")
    }

    @Test("GET /gallery/{n}/strokes tolerates an absent format (older server), defaulting to strokes")
    func galleryPieceStrokesDefaultsFormat() throws {
        let json = Data(#"""
        {
          "strokes": [], "piece_number": 1, "canvas_width": 800, "canvas_height": 600,
          "drawing_style": "plotter"
        }
        """#.utf8)
        let piece = try JSONDecoder().decode(GalleryPieceStrokes.self, from: json)
        #expect(piece.format == .strokes)
        #expect(piece.imageURL == nil)
    }
}
