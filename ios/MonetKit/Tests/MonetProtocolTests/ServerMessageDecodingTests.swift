import Foundation
@testable import MonetProtocol
import Testing

/// Decode coverage for the discriminated-union `ServerMessage` decoder
/// against every message in all three `server/tests/fixtures/*.json`
/// recordings, plus targeted decode-tolerance tests for the fields §10
/// documents as "required, defaults ..." (server Pydantic field defaults),
/// which an older recording can omit entirely. See ../../../ARCHITECTURE.md.
@Suite("ServerMessage decoding")
struct ServerMessageDecodingTests {
    static let fixtureNames = ["agent_turn_plotter.json", "agent_turn_paint.json", "text_chunking_flow.json"]

    @Test("decodes every message type present in every fixture", arguments: fixtureNames)
    func decodesFixture(named name: String) throws {
        let url = Self.fixturesDirectory.appendingPathComponent(name)
        let data = try Data(contentsOf: url)
        // Use JSONSerialization (not a Codable round trip through a generic
        // JSON-value type) so integer fields stay integers — re-encoding a
        // fixture's nested `data` object through a Double-backed JSONValue
        // would turn e.g. `"count": 2` into `"count": 2.0`, which
        // `ServerMessage`'s strict `Int` decoding would then reject.
        let root = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let metadata = try #require(root["metadata"] as? [String: Any])
        let messages = try #require(root["messages"] as? [[String: Any]])
        let declaredCount = try #require(metadata["message_count"] as? Int)
        #expect(messages.count == declaredCount, "\(name): message_count metadata must match messages.length")
        #expect(!messages.isEmpty)

        var unknownTypes = Set<String>()
        var previousTimestamp = -Double.infinity
        for wrapped in messages {
            // Every entry's outer `type` and inner `data.type` must agree
            // (protocol-state spec §10 invariant).
            let outerType = try #require(wrapped["type"] as? String)
            let payload = try #require(wrapped["data"])
            let payloadDict = try #require(payload as? [String: Any])
            let innerType = try #require(payloadDict["type"] as? String)
            #expect(outerType == innerType, "\(name): outer/inner type mismatch")

            // `timestamp_ms` must be monotonically non-decreasing (ties
            // allowed) across the array.
            let timestamp = try #require(wrapped["timestamp_ms"] as? Double)
            #expect(timestamp >= previousTimestamp, "\(name): timestamp_ms went backwards")
            previousTimestamp = timestamp

            let payloadData = try JSONSerialization.data(withJSONObject: payload)
            let message = try JSONDecoder().decode(ServerMessage.self, from: payloadData)
            if case let .unknown(type) = message {
                unknownTypes.insert(type)
            }
        }
        #expect(unknownTypes.isEmpty, "\(name): unrecognized server message types: \(unknownTypes)")
    }

    @Test("gallery entries missing width/height/drawing_style decode with defaults")
    func galleryEntryToleratesMissingFields() throws {
        let json = Data(#"{"id":"p1","created_at":"2026-01-01T00:00:00Z","piece_number":1,"stroke_count":3}"#.utf8)
        let entry = try JSONDecoder().decode(GalleryEntry.self, from: json)
        #expect(entry.width == CanvasDefaults.width)
        #expect(entry.height == CanvasDefaults.height)
        #expect(entry.drawingStyle == .plotter)
    }

    @Test("init missing canvas_width/canvas_height decodes with 800x600 defaults")
    func initPayloadToleratesMissingCanvasSize() throws {
        let json = """
        {"type":"init","strokes":[],"gallery":[],"status":"idle","paused":true,"piece_number":0,
         "monologue":"","drawing_style":"plotter",
         "style_config":{"type":"plotter","name":"Plotter","description":"d",
           "agent_stroke":{"color":"#000","stroke_width":1,"opacity":1,"stroke_linecap":"round","stroke_linejoin":"round"},
           "human_stroke":{"color":"#000","stroke_width":1,"opacity":1,"stroke_linecap":"round","stroke_linejoin":"round"},
           "supports_color":false,"supports_variable_width":false,"supports_opacity":false,"color_palette":null}}
        """
        let message = try JSONDecoder().decode(ServerMessage.self, from: Data(json.utf8))
        guard case let .initial(payload) = message else {
            Issue.record("expected .initial, got \(message)")
            return
        }
        #expect(payload.canvasWidth == CanvasDefaults.width)
        #expect(payload.canvasHeight == CanvasDefaults.height)
    }

    @Test("load_canvas missing drawing_style/canvas size decodes with nil style, 800x600 size")
    func loadCanvasToleratesMissingFields() throws {
        let json = Data(#"{"type":"load_canvas","strokes":[],"piece_number":3}"#.utf8)
        let message = try JSONDecoder().decode(ServerMessage.self, from: json)
        guard case let .loadCanvas(payload) = message else {
            Issue.record("expected .loadCanvas, got \(message)")
            return
        }
        #expect(payload.drawingStyle == nil)
        #expect(payload.canvasWidth == CanvasDefaults.width)
        #expect(payload.canvasHeight == CanvasDefaults.height)
        #expect(payload.styleConfig == nil)
    }

    @Test("unknown type decodes to .unknown, never throws")
    func unknownTypeIsSafe() throws {
        let json = Data(#"{"type":"some_future_message","payload":42}"#.utf8)
        let message = try JSONDecoder().decode(ServerMessage.self, from: json)
        guard case let .unknown(type) = message else {
            Issue.record("expected .unknown, got \(message)")
            return
        }
        #expect(type == "some_future_message")
    }

    /// `server/tests/fixtures` is referenced by path relative to this file,
    /// never copied, per the architect task's verification requirement.
    private static var fixturesDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent() // -> .../MonetKit/Tests/MonetProtocolTests
            .deletingLastPathComponent() // -> .../MonetKit/Tests
            .deletingLastPathComponent() // -> .../MonetKit
            .deletingLastPathComponent() // -> .../ios
            .deletingLastPathComponent() // -> .../ios-swift (repo worktree root)
            .appendingPathComponent("server/tests/fixtures")
    }
}
