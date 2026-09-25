import Foundation
import MonetProtocol
import MonetStudio

/// Pure, SwiftUI-independent presentation logic for the Studio screen (ux
/// spec §6). Kept dependency-free (no SwiftUI/UIKit import) so it is
/// trivially unit-testable — every non-trivial rule from the spec (which
/// ActionBar buttons show, what LiveStatus says, tool copy/icon lookup)
/// lives here rather than being buried in view `body` computations.
enum StudioPresentation {
    // MARK: - Tool copy (ux spec §6.1, §6.3)

    /// The known server tool names (protocol-state spec §2.2's `tool_name`
    /// enum). An unrecognized/`nil` name falls back to a generic
    /// presentation everywhere below.
    enum KnownTool: String {
        case drawPaths = "draw_paths"
        case generateSvg = "generate_svg"
        case viewCanvas = "view_canvas"
        case critiqueCanvas = "critique_canvas"
        case markPieceDone = "mark_piece_done"
        case imagine
        case signCanvas = "sign_canvas"
        case namePiece = "name_piece"
    }

    /// A tool's accent color, expressed as a key rather than a `Color` so
    /// this file stays SwiftUI-free; `StudioColors` maps these to actual
    /// colors.
    enum ToolColorKey: Equatable {
        case primary, purple, muted, sky, success, amber
    }

    struct ToolPresentation: Equatable {
        var icon: String
        var activeIcon: String
        /// `TOOL_DISPLAY_NAMES` value, e.g. "drawing paths" (ux spec §6.1).
        var displayName: String
        var colorKey: ToolColorKey
    }

    /// `TOOL_ICONS`/`TOOL_DISPLAY_NAMES`/`getToolBorderColor` combined (ux
    /// spec §6.1). An unknown tool name gets a generic presentation, same
    /// as the RN app's `TOOL_ICONS.unknown` fallback.
    static func presentation(forToolName toolName: String?) -> ToolPresentation {
        guard let toolName, let tool = KnownTool(rawValue: toolName) else {
            return ToolPresentation(
                icon: "questionmark.circle",
                activeIcon: "questionmark.circle",
                displayName: "Running code",
                colorKey: .primary
            )
        }
        switch tool {
        case .drawPaths:
            return ToolPresentation(icon: "paintbrush.pointed.fill", activeIcon: "paintbrush.pointed", displayName: "drawing paths", colorKey: .primary)
        case .generateSvg:
            return ToolPresentation(icon: "chevron.left.forwardslash.chevron.right", activeIcon: "curlybraces", displayName: "generating SVG", colorKey: .purple)
        case .viewCanvas:
            return ToolPresentation(icon: "eye.fill", activeIcon: "eye", displayName: "viewing canvas", colorKey: .muted)
        case .critiqueCanvas:
            return ToolPresentation(icon: "magnifyingglass.circle.fill", activeIcon: "magnifyingglass", displayName: "critiquing canvas", colorKey: .sky)
        case .markPieceDone:
            return ToolPresentation(icon: "checkmark.seal.fill", activeIcon: "checkmark.seal", displayName: "marking done", colorKey: .success)
        case .imagine:
            return ToolPresentation(icon: "sparkles", activeIcon: "sparkles", displayName: "imagining", colorKey: .amber)
        case .signCanvas:
            return ToolPresentation(icon: "signature", activeIcon: "pencil.and.outline", displayName: "signing", colorKey: .primary)
        case .namePiece:
            return ToolPresentation(icon: "textformat", activeIcon: "character.cursor.ibeam", displayName: "naming piece", colorKey: .primary)
        }
    }

    /// An event bubble's message text still reads as "in progress" (ux spec
    /// §6.1: contains an ellipsis and hasn't yet said "Drew"/"generated").
    /// This governs the icon/label swap to the tool's active/outline
    /// variant.
    static func isInProgress(messageText: String) -> Bool {
        messageText.contains("...") && !messageText.contains("Drew") && !messageText.contains("generated")
    }

    /// The tool driving the current status line, derived from the most
    /// recent `code_execution` message (mirrors the RN app's
    /// `StudioContext.currentTool`, `app/src/context/StudioContext.tsx`).
    static func currentTool(messages: [AgentMessage]) -> String? {
        for message in messages.reversed() where message.type == .codeExecution {
            return message.metadata?.toolName
        }
        return nil
    }

    // MARK: - LiveStatus (ux spec §6.1)

    struct LiveStatusDisplay: Equatable {
        enum Body: Equatable {
            case none
            case event(icon: String, colorKey: ToolColorKey, text: String)
            case thinking(text: String, isBuffering: Bool)
        }

        var icon: String
        var label: String
        var colorKey: ToolColorKey
        var isActive: Bool
        var body: Body
    }

    /// Resolved presentation for whichever tool-call event is currently on
    /// the performance stage, used by `liveStatus(for:)` below.
    private struct EventDisplay {
        var icon: String
        var colorKey: ToolColorKey
        var displayName: String
        var text: String
    }

    /// Returns `nil` exactly when LiveStatus should render nothing (ux spec
    /// §6.1: idle status with no buffered/onstage content).
    static func liveStatus(for state: StudioState) -> LiveStatusDisplay? {
        let status = StudioSelectors.agentStatus(state)
        let performance = state.performance
        let revealedWords = performance.revealedText.split(separator: " ").map(String.init).filter { !$0.isEmpty }

        let eventDisplay: EventDisplay?
        if case let .event(_, message) = performance.onStage {
            let toolName = message.metadata?.toolName
            let tool = presentation(forToolName: toolName)
            let icon = isInProgress(messageText: message.text) ? tool.activeIcon : tool.icon
            eventDisplay = EventDisplay(icon: icon, colorKey: tool.colorKey, displayName: tool.displayName, text: message.text)
        } else {
            eventDisplay = nil
        }

        let hasContent = !revealedWords.isEmpty || !performance.buffer.isEmpty || eventDisplay != nil
        guard status != .idle || hasContent else { return nil }

        let isActive = status == .thinking || status == .executing || status == .drawing
        let tool = currentTool(messages: state.messages)

        let baseLabel = statusLabel(status: status, currentToolName: tool)
        let label = eventDisplay?.displayName ?? baseLabel
        let icon = eventDisplay?.icon ?? statusIcon(status)
        let colorKey: ToolColorKey = eventDisplay?.colorKey ?? (isActive ? .primary : .muted)

        let stageHasMoreWords = totalWordCount(onStage: performance.onStage) > performance.wordIndex
        let bufferHasWords = performance.buffer.contains { if case .words = $0 { true } else { false } }
        let isBuffering = bufferHasWords || stageHasMoreWords

        let body: LiveStatusDisplay.Body
        if let eventDisplay {
            body = .event(icon: eventDisplay.icon, colorKey: eventDisplay.colorKey, text: eventDisplay.text)
        } else if !revealedWords.isEmpty {
            body = .thinking(text: revealedWords.joined(separator: " "), isBuffering: isBuffering)
        } else {
            body = .none
        }

        return LiveStatusDisplay(icon: icon, label: label, colorKey: colorKey, isActive: isActive, body: body)
    }

    private static func totalWordCount(onStage: PerformanceItem?) -> Int {
        guard case let .words(_, text) = onStage else { return 0 }
        return text.split(separator: " ").count
    }

    private static func statusIcon(_ status: AgentStatus) -> String {
        switch status {
        case .idle: "circle"
        case .thinking: "lightbulb.fill"
        case .drawing: "paintbrush.pointed.fill"
        case .executing: "chevron.left.forwardslash.chevron.right"
        case .paused: "pause.fill"
        case .error: "exclamationmark.triangle.fill"
        }
    }

    /// `getStatusLabel` (ux spec §6.1). Only `.executing` consults
    /// `currentToolName`; every other status ignores it.
    private static func statusLabel(status: AgentStatus, currentToolName: String?) -> String {
        if status == .executing, let currentToolName {
            return presentation(forToolName: currentToolName).displayName
        }
        switch status {
        case .thinking: return "Thinking"
        case .drawing: return "Drawing"
        case .executing: return "Running code"
        case .paused: return "Paused"
        case .error: return "Error"
        case .idle: return ""
        }
    }

    // MARK: - ActionBar (ux spec §6.4)

    struct ActionBarButton: Equatable, Identifiable {
        enum Kind: String {
            case draw, nudge, home, gallery, pause
        }

        var kind: Kind
        var id: String { kind.rawValue }
        var icon: String
        var label: String
        var active: Bool
        var disabled: Bool
    }

    /// The dynamic 5/3/2-button set (ux spec §6.4): normal running state
    /// shows all five, paused drops Draw+Nudge, view-only drops
    /// Draw+Nudge+Pause. Takes primitives rather than a whole `StudioState`
    /// so it stays testable independent of how each flag is sourced —
    /// notably `drawingEnabled`, which `StudioState` models but which
    /// `StudioStore` (networking+auth-owned) does not yet expose a way to
    /// mutate; `StudioView` tracks it as view-local state instead (see its
    /// doc comment) and passes it in here like any other flag.
    static func actionBarButtons(
        paused: Bool,
        viewOnly: Bool,
        drawingEnabled: Bool,
        connected: Bool,
        galleryCount: Int
    ) -> [ActionBarButton] {
        var buttons: [ActionBarButton] = []

        if !paused, !viewOnly {
            buttons.append(ActionBarButton(
                kind: .draw,
                icon: drawingEnabled ? "pencil" : "pencil.slash",
                label: "Draw",
                active: drawingEnabled,
                disabled: !connected
            ))
            buttons.append(ActionBarButton(
                kind: .nudge,
                icon: "bubble.left",
                label: "Nudge",
                active: false,
                disabled: !connected
            ))
        }

        buttons.append(ActionBarButton(kind: .home, icon: "house", label: "Home", active: false, disabled: false))
        buttons.append(ActionBarButton(
            kind: .gallery,
            icon: "photo.on.rectangle",
            label: "Gallery",
            active: false,
            disabled: galleryCount == 0
        ))

        if !viewOnly {
            buttons.append(ActionBarButton(
                kind: .pause,
                icon: paused ? "play.fill" : "pause.fill",
                label: paused ? "Start" : "Pause",
                active: paused,
                disabled: !connected
            ))
        }

        return buttons
    }

    // MARK: - Misc formatting

    /// `formatTime` (ux spec §6.3): local short time, e.g. "3:45 PM".
    static func formatTime(epochMilliseconds: Double) -> String {
        let date = Date(timeIntervalSince1970: epochMilliseconds / 1000)
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        formatter.dateStyle = .none
        return formatter.string(from: date)
    }

    /// `getCodeFromInput` (ux spec §6.3): extracts a `generate_svg` call's
    /// `code` field for the expandable "Python Code" section, if present.
    static func code(fromToolInput toolInput: JSONValue?) -> String? {
        guard case let .object(fields) = toolInput, case let .string(code) = fields["code"] else { return nil }
        return code
    }
}
