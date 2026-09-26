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
    /// For `name_piece`: the title from the call's input.
    public var title: String?

    public init(
        toolName: String?,
        inProgress: Bool,
        failed: Bool = false,
        durationMs: Double? = nil,
        producedVersion: Int? = nil,
        title: String? = nil
    ) {
        self.toolName = toolName
        self.inProgress = inProgress
        self.failed = failed
        self.durationMs = durationMs
        self.producedVersion = producedVersion
        self.title = title
    }

    /// The server's own tools; everything else (SDK built-ins such as Read,
    /// Bash, ToolSearch) is housekeeping.
    public static let domainTools: Set<String> = [
        "paint", "critique_canvas", "name_piece", "view_canvas", "imagine",
        "sign_canvas", "mark_piece_done", "draw_paths", "generate_svg",
    ]

    public var isDomain: Bool { toolName.map(Self.domainTools.contains) ?? false }
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
        /// Display-only (`Notebook.grouped`): a run of consecutive
        /// housekeeping tool calls, as distinct lowercase names in
        /// first-seen order.
        case housekeeping([String])
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

    /// The display view of `entries`: each run of consecutive housekeeping
    /// tool calls (same version) collapses into one `.housekeeping` entry.
    /// The underlying entries are untouched — this is derived per render.
    public static func grouped(_ entries: [NotebookEntry]) -> [NotebookEntry] {
        var result: [NotebookEntry] = []
        for entry in entries {
            guard case let .tool(call) = entry.kind, !call.isDomain else {
                result.append(entry)
                continue
            }
            let name = (call.toolName ?? "tool").lowercased()
            if var last = result.last, case let .housekeeping(names) = last.kind, last.version == entry.version {
                if !names.contains(name) { last.kind = .housekeeping(names + [name]) }
                result[result.count - 1] = last
            } else {
                result.append(NotebookEntry(id: entry.id, version: entry.version, kind: .housekeeping([name])))
            }
        }
        return result
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
                    producedVersion: producedVersion(toolName: toolName, version: message.version),
                    title: Self.inputTitle(message)
                )
                open.append((toolName, entries.count, message.timestamp))
                append(message, .tool(call))
                return
            }
            let failed = (message.metadata?.returnCode ?? 0) != 0
            guard let openIndex = open.lastIndex(where: { $0.toolName == toolName }) else {
                // Its `started` was dropped from the bounded message list.
                let call = NotebookToolCall(toolName: toolName, inProgress: false, failed: failed, title: Self.inputTitle(message))
                entries.append(completedEntry(id: message.id, version: message.version, call: call, message: message))
                return
            }
            let started = open.remove(at: openIndex)
            let existing = entries[started.index]
            var startedTitle: String?
            if case let .tool(startedCall) = existing.kind { startedTitle = startedCall.title }
            let call = NotebookToolCall(
                toolName: toolName,
                inProgress: false,
                failed: failed,
                durationMs: max(0, message.timestamp - started.startedAt),
                producedVersion: failed ? nil : producedVersion(toolName: toolName, version: existing.version),
                title: Self.inputTitle(message) ?? startedTitle
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

        private static func inputTitle(_ message: AgentMessage) -> String? {
            guard message.metadata?.toolName == "name_piece",
                  case let .object(fields)? = message.metadata?.toolInput,
                  case let .string(title)? = fields["title"] else { return nil }
            let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed.isEmpty ? nil : trimmed
        }

        /// A `paint` call stamped "work toward vN" produced vN if vN exists.
        private func producedVersion(toolName: String?, version: Int?) -> Int? {
            guard toolName == "paint", let version, knownVersions.contains(version) else { return nil }
            return version
        }
    }
}
