import Foundation
import Testing
@testable import MonetProtocol

/// Smoke coverage for the discriminated-union decoder. The protocol+studio
/// work package (see ../../../ARCHITECTURE.md) is expected to grow this into
/// full fixture-replay coverage against every message in
/// `server/tests/fixtures/*.json` — this stub proves the wiring compiles and
/// the fixture path resolves, and is a template for that expansion.
@Suite("ServerMessage decoding")
struct ServerMessageDecodingTests {
    @Test("decodes every message type present in the plotter fixture")
    func decodesPlotterFixture() throws {
        let url = Self.fixturesDirectory.appendingPathComponent("agent_turn_plotter.json")
        let data = try Data(contentsOf: url)
        // Use JSONSerialization (not a Codable round trip through a generic
        // JSON-value type) so integer fields stay integers — re-encoding a
        // fixture's nested `data` object through a Double-backed JSONValue
        // would turn e.g. `"count": 2` into `"count": 2.0`, which
        // `ServerMessage`'s strict `Int` decoding would then reject.
        let root = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let messages = try #require(root["messages"] as? [[String: Any]])
        #expect(messages.count > 0)
        var unknownTypes = Set<String>()
        for wrapped in messages {
            let payload = try #require(wrapped["data"])
            let payloadData = try JSONSerialization.data(withJSONObject: payload)
            let message = try JSONDecoder().decode(ServerMessage.self, from: payloadData)
            if case let .unknown(type) = message {
                unknownTypes.insert(type)
            }
        }
        #expect(unknownTypes.isEmpty, "Unrecognized server message types: \(unknownTypes)")
    }

    @Test("unknown type decodes to .unknown, never throws")
    func unknownTypeIsSafe() throws {
        let json = #"{"type":"some_future_message","payload":42}"#.data(using: .utf8)!
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
