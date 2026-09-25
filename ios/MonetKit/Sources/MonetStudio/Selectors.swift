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
    /// drawing > idle.
    public static func agentStatus(_ state: StudioState) -> AgentStatus {
        if state.paused { return .paused }
        if state.messages.last?.type == .error { return .error }
        if hasWordsPending(state) { return .thinking }
        if hasEventOnStage(state) || hasUnmatchedCodeExecutionStarted(state) { return .executing }
        if hasStrokesPending(state) { return .drawing }
        return .idle
    }

    /// Shown only while nothing at all has been drawn yet (protocol-state
    /// spec §11.7) — hidden the instant the agent's pen starts moving.
    public static func shouldShowIdleAnimation(_ state: StudioState) -> Bool {
        state.strokes.isEmpty && state.currentStroke.isEmpty && state.performance.agentStroke.isEmpty
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

    private static func hasUnmatchedCodeExecutionStarted(_ state: StudioState) -> Bool {
        var started: Set<String> = []
        for message in state.messages where message.type == .codeExecution {
            guard let tool = message.metadata?.toolName else { continue }
            if message.status == .started {
                started.insert(tool)
            } else if message.status == .completed {
                started.remove(tool)
            }
        }
        return !started.isEmpty
    }
}
