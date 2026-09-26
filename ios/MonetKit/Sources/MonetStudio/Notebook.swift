import MonetProtocol

/// One tool call in the Studio notebook: a `code_execution` started/completed
/// pair collapsed into a single line.
public struct NotebookToolCall: Equatable, Sendable {
    public var toolName: String?
    public var inProgress: Bool
    public var failed: Bool
    /// Client-measured wall time between the started and completed messages.
    public var durationMs: Double?
    /// For `paint`: the version this call produced, once it has arrived.
    public var producedVersion: Int?

    public init(
        toolName: String?,
        inProgress: Bool,
        failed: Bool = false,
        durationMs: Double? = nil,
        producedVersion: Int? = nil
    ) {
        self.toolName = toolName
        self.inProgress = inProgress
        self.failed = failed
        self.durationMs = durationMs
        self.producedVersion = producedVersion
    }
}

/// One entry in the Studio notebook (the redesign's replacement for the
/// chat-bubble message stream).
public struct NotebookEntry: Equatable, Sendable, Identifiable {
    public enum Kind: Equatable, Sendable {
        case thought(String)
        case tool(NotebookToolCall)
        /// A completed `critique_canvas` call's output.
        case critique(String)
        /// Something the user sent from this device.
        case nudge(String)
        case error(message: String, detail: String?)
        case pieceComplete(Int?)
    }

    public var id: String
    /// The painting version this entry is work toward (see
    /// `AgentMessage.version`).
    public var version: Int?
    public var kind: Kind
    /// The still-streaming thought at the end of the notebook.
    public var isLive: Bool

    public init(id: String, version: Int?, kind: Kind, isLive: Bool = false) {
        self.id = id
        self.version = version
        self.kind = kind
        self.isLive = isLive
    }
}

/// Builds notebook entries from reducer state. Pure; safe to call per render.
public enum Notebook {
    public static let liveThoughtID = "notebook-live-thought"

    public static func entries(_ state: StudioState) -> [NotebookEntry] {
        entries(
            messages: state.messages,
            liveThinking: state.thinking,
            versions: state.versions,
            workingVersion: state.workingVersion
        )
    }

    public static func entries(
        messages: [AgentMessage],
        liveThinking: String,
        versions: [PaintingVersionSummary],
        workingVersion: Int
    ) -> [NotebookEntry] {
        var builder = Builder(knownVersions: Set(versions.map(\.version)))
        for message in messages {
            builder.add(message)
        }
        let live = liveThinking.trimmingCharacters(in: .whitespacesAndNewlines)
        if !live.isEmpty {
            builder.entries.append(NotebookEntry(
                id: liveThoughtID, version: workingVersion, kind: .thought(live), isLive: true
            ))
        }
        return settleSupersededCalls(builder.entries)
    }

    /// The server broadcasts `completed` only for its own drawing tools, so
    /// other tools (SDK built-ins like `Bash`) never close. A call counts as
    /// running only while it's the notebook's last entry — anything after it
    /// (a thought, another call) means the agent has moved on.
    private static func settleSupersededCalls(_ entries: [NotebookEntry]) -> [NotebookEntry] {
        entries.enumerated().map { index, entry in
            guard index < entries.count - 1, case var .tool(call) = entry.kind, call.inProgress else { return entry }
            call.inProgress = false
            var settled = entry
            settled.kind = .tool(call)
            return settled
        }
    }

    /// The tool call running right now, if the notebook ends with one.
    public static func runningTool(_ entries: [NotebookEntry]) -> NotebookToolCall? {
        guard case let .tool(call)? = entries.last?.kind, call.inProgress else { return nil }
        return call
    }

    private struct Builder {
        let knownVersions: Set<Int>
        var entries: [NotebookEntry] = []
        /// Open (started, not yet completed) tool calls: entry index + start time.
        private var open: [(toolName: String?, index: Int, startedAt: Double)] = []

        init(knownVersions: Set<Int>) {
            self.knownVersions = knownVersions
        }

        mutating func add(_ message: AgentMessage) {
            switch message.type {
            case .thinking, .thinkingDelta:
                let text = message.text.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !text.isEmpty else { return }
                append(message, .thought(text))
            case .userNudge:
                append(message, .nudge(message.text))
            case .error:
                append(message, .error(message: message.text, detail: message.metadata?.stderr))
            case .pieceComplete:
                append(message, .pieceComplete(message.metadata?.pieceNumber))
            case .codeExecution:
                addTool(message)
            case .iteration:
                return
            }
        }

        private mutating func append(_ message: AgentMessage, _ kind: NotebookEntry.Kind) {
            entries.append(NotebookEntry(id: message.id, version: message.version, kind: kind))
        }

        private mutating func addTool(_ message: AgentMessage) {
            let toolName = message.metadata?.toolName
            if message.status == .started {
                let call = NotebookToolCall(
                    toolName: toolName,
                    inProgress: true,
                    producedVersion: producedVersion(toolName: toolName, version: message.version)
                )
                open.append((toolName, entries.count, message.timestamp))
                append(message, .tool(call))
                return
            }
            let failed = (message.metadata?.returnCode ?? 0) != 0
            guard let openIndex = open.lastIndex(where: { $0.toolName == toolName }) else {
                // Its `started` was dropped from the bounded message list.
                let call = NotebookToolCall(toolName: toolName, inProgress: false, failed: failed)
                entries.append(completedEntry(id: message.id, version: message.version, call: call, message: message))
                return
            }
            let started = open.remove(at: openIndex)
            let existing = entries[started.index]
            let call = NotebookToolCall(
                toolName: toolName,
                inProgress: false,
                failed: failed,
                durationMs: max(0, message.timestamp - started.startedAt),
                producedVersion: failed ? nil : producedVersion(toolName: toolName, version: existing.version)
            )
            entries[started.index] = completedEntry(id: existing.id, version: existing.version, call: call, message: message)
        }

        /// A successful critique reads as its verdict, not as a tool line.
        private func completedEntry(id: String, version: Int?, call: NotebookToolCall, message: AgentMessage) -> NotebookEntry {
            if call.toolName == "critique_canvas", !call.failed,
               let output = message.metadata?.stdout?.trimmingCharacters(in: .whitespacesAndNewlines), !output.isEmpty {
                return NotebookEntry(id: id, version: version, kind: .critique(output))
            }
            return NotebookEntry(id: id, version: version, kind: .tool(call))
        }

        /// A `paint` call stamped "work toward vN" produced vN if vN exists.
        private func producedVersion(toolName: String?, version: Int?) -> Int? {
            guard toolName == "paint", let version, knownVersions.contains(version) else { return nil }
            return version
        }
    }
}
