import Foundation
@testable import MonetProtocol
import Testing

/// Decode coverage for the program-painting wire additions: the
/// `painting_version`, `painting_live` and `painting_live_failed` server
/// messages, `init.painting`/`init.painting_live`, and the raster gallery
/// fields.
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

    @Test("decodes painting_live and painting_live_failed")
    func decodesLiveMessages() throws {
        let live = try JSONDecoder().decode(ServerMessage.self, from: Data(#"""
        {"type": "painting_live", "piece_number": 12, "asset_base": "/painting-assets/u/tok/",
         "image_width": 1600, "image_height": 1200}
        """#.utf8))
        #expect(live == .paintingLive(PaintingLiveRef(
            pieceNumber: 12, assetBase: "/painting-assets/u/tok/", imageWidth: 1600, imageHeight: 1200
        )))
        let failed = try JSONDecoder().decode(ServerMessage.self, from: Data(#"""
        {"type": "painting_live_failed", "piece_number": 12, "asset_base": "/painting-assets/u/tok/"}
        """#.utf8))
        #expect(failed == .paintingLiveFailed(pieceNumber: 12, assetBase: "/painting-assets/u/tok/"))
    }

    @Test("init.painting_live seeds the streaming run; absent, null or malformed read as nil")
    func decodesInitPaintingLive() throws {
        func payload(_ extra: String) throws -> InitPayload {
            let json = Data("""
            {
              "type": "init",
              "strokes": [], "gallery": [], "status": "idle", "paused": false,
              "piece_number": 12, "canvas_width": 800, "canvas_height": 600,
              "monologue": "", "drawing_style": "paint", "style_config": \(Self.styleConfigJSON)\(extra)
            }
            """.utf8)
            guard case let .initial(payload) = try JSONDecoder().decode(ServerMessage.self, from: json) else {
                throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "expected init"))
            }
            return payload
        }
        let live = try payload(#", "painting_live": {"piece_number": 12, "asset_base": "/a/", "image_width": 1600, "image_height": 1200}"#)
        #expect(live.paintingLive == PaintingLiveRef(pieceNumber: 12, assetBase: "/a/", imageWidth: 1600, imageHeight: 1200))
        #expect(try payload("").paintingLive == nil)
        #expect(try payload(#", "painting_live": null"#).paintingLive == nil)
        #expect(try payload(#", "painting_live": {"piece_number": "x"}"#).paintingLive == nil)
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
