import Foundation
@testable import MonetProtocol
import Testing

/// Decode coverage for the additive piece-history fields (init title/prompt/
/// versions, `painting_version.ops`, gallery detail title/prompt/
/// stroke_count/versions): present and absent.
@Suite("Piece history decoding")
struct PieceHistoryDecodingTests {
    private static let styleConfigJSON = PaintingVersionDecodingTests.styleConfigJSON

    private func decodeInit(_ extra: String, painting: String = "null") throws -> InitPayload {
        let json = Data("""
        {
          "type": "init", "strokes": [], "gallery": [], "status": "idle", "paused": true,
          "piece_number": 12, "canvas_width": 800, "canvas_height": 600, "monologue": "",
          "drawing_style": "paint", "style_config": \(Self.styleConfigJSON),
          "painting": \(painting)\(extra)
        }
        """.utf8)
        guard case let .initial(payload) = try JSONDecoder().decode(ServerMessage.self, from: json) else {
            Issue.record("expected .initial")
            throw CancellationError()
        }
        return payload
    }

    private static let paintingWithHistory = """
        {
          "piece_number": 12, "version": 2, "asset_base": "/painting-assets/u/t2/",
          "image_width": 1600, "image_height": 1200,
          "versions": [
            {"version": 1, "asset_base": "/painting-assets/u/t1/", "image_width": 1600, "image_height": 1200,
             "stages": ["ground", "sky"], "ops": 2100, "created_at": "2026-09-26T12:00:00+00:00"},
            {"version": 2, "asset_base": "/painting-assets/u/t2/", "image_width": 1600, "image_height": 1200,
             "stages": ["ground", "sky", "boat"], "ops": 3050, "created_at": "2026-09-26T12:05:00+00:00"}
          ],
          "prompt": "a stormy sea"
        }
        """

    @Test("init decodes title, prompt, and painting.versions when present")
    func initDecodesHistory() throws {
        let payload = try decodeInit(#", "title": "Storm", "prompt": "a stormy sea""#, painting: Self.paintingWithHistory)
        #expect(payload.title == "Storm")
        #expect(payload.prompt == "a stormy sea")
        #expect(payload.painting?.version == 2)
        #expect(payload.paintingVersions.map(\.version) == [1, 2])
        #expect(payload.paintingVersions[0].stages == ["ground", "sky"])
        #expect(payload.paintingVersions[1].ops == 3050)
        #expect(payload.paintingVersions[0].createdAt == "2026-09-26T12:00:00+00:00")
    }

    @Test("init falls back to painting.prompt when top-level prompt is absent")
    func initPromptFallsBackToPaintingPrompt() throws {
        let payload = try decodeInit("", painting: Self.paintingWithHistory)
        #expect(payload.prompt == "a stormy sea")
        #expect(payload.title == nil)
    }

    @Test("init from an older server: no title, prompt, or versions")
    func initWithoutHistoryFields() throws {
        let painting = """
            {"piece_number": 12, "version": 3, "asset_base": "/painting-assets/u/t/", "image_width": 1600, "image_height": 1200}
            """
        let payload = try decodeInit("", painting: painting)
        #expect(payload.title == nil)
        #expect(payload.prompt == nil)
        #expect(payload.paintingVersions.isEmpty)
        #expect(payload.painting?.version == 3)

        let blank = try decodeInit(#", "title": null, "prompt": null"#)
        #expect(blank.painting == nil)
        #expect(blank.paintingVersions.isEmpty)
    }

    @Test("painting_version decodes ops when present")
    func paintingVersionDecodesOps() throws {
        let json = Data(#"""
        {"type": "painting_version", "piece_number": 1, "version": 4, "asset_base": "/painting-assets/u/t/",
         "image_width": 1600, "image_height": 1200, "stages": ["ground"], "ops": 318}
        """#.utf8)
        guard case let .paintingVersion(ref, stages, ops) = try JSONDecoder().decode(ServerMessage.self, from: json) else {
            Issue.record("expected .paintingVersion")
            return
        }
        #expect(ref.version == 4)
        #expect(stages == ["ground"])
        #expect(ops == 318)
    }

    @Test("gallery piece detail decodes title, prompt, stroke_count, versions when present")
    func galleryDetailWithHistory() throws {
        let json = Data("""
        {"strokes": [], "piece_number": 7, "canvas_width": 800, "canvas_height": 600,
         "drawing_style": "paint", "style_config": null, "format": "raster",
         "image_url": "/painting-assets/u/t2/final.png",
         "title": "Lilies", "prompt": "water lilies", "stroke_count": 3050,
         "versions": [
           {"version": 1, "asset_base": "/painting-assets/u/t1/", "image_width": 1600, "image_height": 1200,
            "stages": ["ground"], "ops": 900, "created_at": "2026-09-26T12:00:00+00:00"},
           {"version": 2, "asset_base": "/painting-assets/u/t2/", "image_width": 1600, "image_height": 1200,
            "stages": ["ground", "pads"], "ops": 3050, "created_at": "2026-09-26T12:04:00+00:00"}
         ]}
        """.utf8)
        let detail = try JSONDecoder().decode(GalleryPieceStrokes.self, from: json)
        #expect(detail.title == "Lilies")
        #expect(detail.prompt == "water lilies")
        #expect(detail.strokeCount == 3050)
        #expect(detail.versions.map(\.assetBase) == ["/painting-assets/u/t1/", "/painting-assets/u/t2/"])
    }

    @Test("gallery piece detail from an older server decodes with history fields empty")
    func galleryDetailWithoutHistory() throws {
        let json = Data("""
        {"strokes": [], "piece_number": 7, "canvas_width": 800, "canvas_height": 600,
         "drawing_style": "plotter", "style_config": null}
        """.utf8)
        let detail = try JSONDecoder().decode(GalleryPieceStrokes.self, from: json)
        #expect(detail.title == nil)
        #expect(detail.prompt == nil)
        #expect(detail.strokeCount == nil)
        #expect(detail.versions.isEmpty)
        #expect(detail.format == .strokes)
    }

    @Test("a version summary tolerates missing optional keys")
    func versionSummaryTolerant() throws {
        let json = Data(#"{"version": 1, "asset_base": "/painting-assets/u/t/"}"#.utf8)
        let summary = try JSONDecoder().decode(PaintingVersionSummary.self, from: json)
        #expect(summary.stages.isEmpty)
        #expect(summary.ops == nil)
        #expect(summary.createdAt == nil)
        #expect(summary.ref(pieceNumber: 3).pieceNumber == 3)
    }

    @Test("strokeOpCount counts only stroke ops")
    func strokeOpCount() {
        let manifest = RevealManifest(width: 10, height: 10, keyframes: [
            RevealKeyframe(label: "ground", image: "kf_00.jpg", ops: [
                .area(x0: 0, y0: 0, x1: 10, y1: 10),
                .stroke(width: 2, points: [Point(x: 1, y: 1)]),
            ]),
            RevealKeyframe(label: "sky", image: "kf_01.jpg", ops: [
                .stroke(width: 2, points: [Point(x: 1, y: 1), Point(x: 2, y: 2)]),
            ]),
        ])
        #expect(manifest.strokeOpCount == 2)
    }
}

@Suite("Lossy version decoding")
struct LossyVersionDecodingTests {
    @Test("one malformed version entry doesn't fail init; the rest decode")
    func initSkipsBadVersion() throws {
        let json = Data("""
        {
          "type": "init", "strokes": [], "gallery": [], "status": "idle", "paused": true,
          "piece_number": 2, "canvas_width": 800, "canvas_height": 600, "monologue": "",
          "drawing_style": "paint", "style_config": \(PaintingVersionDecodingTests.styleConfigJSON),
          "painting": {
            "piece_number": 2, "version": 2, "asset_base": "/a/2/", "image_width": 10, "image_height": 10,
            "versions": [
              {"version": 1, "asset_base": "/a/1/"},
              {"version": "two", "asset_base": 5},
              {"version": 2, "asset_base": "/a/2/", "ops": 20}
            ]
          }
        }
        """.utf8)
        guard case let .initial(payload) = try JSONDecoder().decode(ServerMessage.self, from: json) else {
            Issue.record("expected .initial")
            return
        }
        #expect(payload.paintingVersions.map(\.version) == [1, 2])
        #expect(payload.painting?.version == 2)
    }

    @Test("one malformed version entry doesn't fail gallery detail; a non-array versions reads as empty")
    func galleryDetailSkipsBadVersion() throws {
        let base = """
        "strokes": [], "piece_number": 7, "canvas_width": 800, "canvas_height": 600, "drawing_style": "paint", "style_config": null
        """
        let detail = try JSONDecoder().decode(GalleryPieceStrokes.self, from: Data("""
        {\(base), "versions": [null, {"version": 3, "asset_base": "/a/3/"}, {"asset_base": "/a/x/"}]}
        """.utf8))
        #expect(detail.versions.map(\.version) == [3])
        let wrongType = try JSONDecoder().decode(GalleryPieceStrokes.self, from: Data("{\(base), \"versions\": \"nope\"}".utf8))
        #expect(wrongType.versions.isEmpty)
    }
}
