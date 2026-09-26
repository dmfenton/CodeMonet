import MonetProtocol

/// Derived, never server-sent (protocol-state spec §1.3, §5.4's `init`
/// note). The client always computes this itself rather than trusting the
/// server's `init.status` string.
public enum AgentStatus: Equatable, Sendable {
    case idle
    case thinking
    case executing
    case drawing
    case paused
    case error
}

/// Pure derived selectors over `StudioState` (protocol-state spec §11.8,
/// ux spec §2). All are `O(small)` snapshots safe to call on every render.
public enum StudioSelectors {
    /// Priority: paused > error(last message) > thinking > executing >
    /// drawing > idle — except that while the server reports an agent turn
    /// in progress (`turnActive`), "idle" reads as thinking: the painter is
    /// working through a silent gap, or we reconnected mid-turn.
    public static func agentStatus(_ state: StudioState) -> AgentStatus {
        if state.paused { return .paused }
        if state.messages.last?.type == .error { return .error }
        if hasWordsPending(state) { return .thinking }
        if hasEventOnStage(state) || hasInProgressEvents(state) { return .executing }
        if hasStrokesPending(state) { return .drawing }
        // A program-painting reveal in progress also counts as "drawing"
        // (program-painting spec §4.1 `deriveAgentStatus`).
        if state.painting.playing != nil { return .drawing }
        return state.turnActive ? .thinking : .idle
    }

    /// Shown only while nothing at all has been drawn yet (protocol-state
    /// spec §11.7) — hidden the instant the agent's pen starts moving.
    /// Additionally hidden whenever any program painting is present, base
    /// or playing (program-painting spec §4.1 `shouldShowIdleAnimation`).
    public static func shouldShowIdleAnimation(_ state: StudioState) -> Bool {
        state.strokes.isEmpty
            && state.currentStroke.isEmpty
            && state.performance.agentStroke.isEmpty
            && !hasPainting(state.painting)
    }

    private static func hasWordsPending(_ state: StudioState) -> Bool {
        if case .words = state.performance.onStage { return true }
        return state.performance.buffer.contains { if case .words = $0 { true } else { false } }
    }

    private static func hasEventOnStage(_ state: StudioState) -> Bool {
        if case .event = state.performance.onStage { return true }
        return false
    }

    private static func hasStrokesPending(_ state: StudioState) -> Bool {
        if case .strokes = state.performance.onStage { return true }
        return state.performance.buffer.contains { if case .strokes = $0 { true } else { false } }
    }

    /// `hasInProgressEvents` (protocol-state spec §8): builds the set of
    /// `"{tool_name}_{iteration}"` keys for every completed
    /// `code_execution` message, then checks whether any *started* message's
    /// key is missing from that set. The key MUST include `iteration`, not
    /// just `toolName` — otherwise a `completed` for the same tool in a
    /// *later* iteration would incorrectly clear an unmatched `started` from
    /// an *earlier* iteration (two-pass set-membership check, not a
    /// running insert/remove counter, which conflates same-named tools
    /// across iterations). Public (not just an `agentStatus` implementation
    /// detail) because the spec names it as an independently-meaningful
    /// selector and its own replay-test assertion checks it directly rather
    /// than the folded-together `agentStatus` (protocol-state spec §10.1).
    public static func hasInProgressEvents(_ state: StudioState) -> Bool {
        var completedKeys: Set<String> = []
        for message in state.messages
            where message.type == .codeExecution && message.status == .completed {
            let tool = message.metadata?.toolName ?? "unknown"
            completedKeys.insert("\(tool)_\(message.iteration ?? 0)")
        }
        for message in state.messages
            where message.type == .codeExecution && message.status == .started {
            let tool = message.metadata?.toolName ?? "unknown"
            if !completedKeys.contains("\(tool)_\(message.iteration ?? 0)") {
                return true
            }
        }
        return false
    }
}
