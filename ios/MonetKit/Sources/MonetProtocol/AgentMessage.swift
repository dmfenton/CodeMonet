import Foundation

/// The event-history panel's entry kind (ux spec §6.3 "Thoughts" stream).
public enum AgentMessageType: String, Codable, Equatable, Sendable {
    case thinking
    case thinkingDelta = "thinking_delta"
    case error
    case pieceComplete = "piece_complete"
    case codeExecution = "code_execution"
    case iteration
    /// A nudge (or starting direction) the user sent from this device —
    /// client-local, never on the wire as a message of its own.
    case userNudge = "user_nudge"
}

public enum ToolExecutionStatus: String, Codable, Equatable, Sendable {
    case started
    case completed
}

/// Optional per-message payload. Every field is independently optional —
/// which ones are populated depends on `AgentMessage.type`.
public struct AgentMessageMetadata: Codable, Equatable, Sendable {
    public var toolName: String?
    public var toolInput: JSONValue?
    public var stdout: String?
    public var stderr: String?
    public var returnCode: Int?
    public var pieceNumber: Int?
    public var currentIteration: Int?
    public var maxIterations: Int?

    public init(
        toolName: String? = nil,
        toolInput: JSONValue? = nil,
        stdout: String? = nil,
        stderr: String? = nil,
        returnCode: Int? = nil,
        pieceNumber: Int? = nil,
        currentIteration: Int? = nil,
        maxIterations: Int? = nil
    ) {
        self.toolName = toolName
        self.toolInput = toolInput
        self.stdout = stdout
        self.stderr = stderr
        self.returnCode = returnCode
        self.pieceNumber = pieceNumber
        self.currentIteration = currentIteration
        self.maxIterations = maxIterations
    }

    enum CodingKeys: String, CodingKey {
        case toolName = "tool_name"
        case toolInput = "tool_input"
        case stdout, stderr
        case returnCode = "return_code"
        case pieceNumber = "piece_number"
        case currentIteration = "current_iteration"
        case maxIterations = "max_iterations"
    }
}

/// One entry in the studio's "Thoughts" event-history panel (bounded to the
/// last `StudioState.maxMessages`, oldest dropped first). Built client-side
/// from routed server messages — never decoded directly off the wire as a
/// single type (see `MonetStudio`'s message-routing table).
public struct AgentMessage: Codable, Equatable, Sendable, Identifiable {
    public var id: String
    public var type: AgentMessageType
    public var text: String
    /// Epoch milliseconds, matching the TS `timestamp: number`.
    public var timestamp: Double
    public var iteration: Int?
    public var status: ToolExecutionStatus?
    public var metadata: AgentMessageMetadata?
    /// The painting version this entry is work toward (`N` for everything
    /// after v(N-1) arrived). Stamped by the reducer when the message is
    /// added; `nil` on a message not yet reduced.
    public var version: Int?

    public init(
        id: String,
        type: AgentMessageType,
        text: String,
        timestamp: Double,
        iteration: Int? = nil,
        status: ToolExecutionStatus? = nil,
        metadata: AgentMessageMetadata? = nil,
        version: Int? = nil
    ) {
        self.id = id
        self.type = type
        self.text = text
        self.timestamp = timestamp
        self.iteration = iteration
        self.status = status
        self.metadata = metadata
        self.version = version
    }
}

/// A minimal untyped-JSON value, used only for `tool_input` (arbitrary
/// shape depending on `tool_name`) so we never need a full JSON AST
/// dependency in this package. Decodes/encodes losslessly for the shapes the
/// server actually sends (objects/arrays/strings/numbers/bools/null).
public indirect enum JSONValue: Codable, Equatable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            self = .null
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case let .string(value): try container.encode(value)
        case let .number(value): try container.encode(value)
        case let .bool(value): try container.encode(value)
        case let .object(value): try container.encode(value)
        case let .array(value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }
}
