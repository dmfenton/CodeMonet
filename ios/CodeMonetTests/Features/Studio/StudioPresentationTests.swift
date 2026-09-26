import Foundation
import MonetProtocol
import MonetStudio
import Testing
@testable import CodeMonet

/// Coverage for `StudioPresentation`'s pure derivation rules (ux spec §6) —
/// the ActionBar's dynamic 5/3/2 button set, LiveStatus's visibility/label/
/// icon logic, and the small tool-copy helpers. Kept independent of
/// SwiftUI/XCUITest so it runs fast on every `make test-app` pass.
@Suite("StudioPresentation")
struct StudioPresentationTests {
    // MARK: - ActionBar button set (ux spec §6.4)

    @Test("Normal running state shows all five buttons in order")
    func actionBarNormalState() {
        let buttons = StudioPresentation.actionBarButtons(
            paused: false, viewOnly: false, drawingEnabled: false, connected: true, galleryCount: 3
        )
        #expect(buttons.map(\.kind) == [.draw, .nudge, .home, .gallery, .pause])
    }

    @Test("Paused state drops Draw and Nudge, leaving Home, Gallery, Start")
    func actionBarPausedState() {
        let buttons = StudioPresentation.actionBarButtons(
            paused: true, viewOnly: false, drawingEnabled: false, connected: true, galleryCount: 3
        )
        #expect(buttons.map(\.kind) == [.home, .gallery, .pause])
        let pause = buttons.first { $0.kind == .pause }
        #expect(pause?.label == "Start")
        #expect(pause?.active == true)
    }

    @Test("View-only state drops Draw, Nudge, and Pause, leaving Home and Gallery")
    func actionBarViewOnlyState() {
        let buttons = StudioPresentation.actionBarButtons(
            paused: false, viewOnly: true, drawingEnabled: false, connected: true, galleryCount: 3
        )
        #expect(buttons.map(\.kind) == [.home, .gallery])
    }

    @Test("Gallery button is disabled only when the gallery is empty")
    func actionBarGalleryDisabledWhenEmpty() {
        let empty = StudioPresentation.actionBarButtons(paused: false, viewOnly: false, drawingEnabled: false, connected: true, galleryCount: 0)
        let nonEmpty = StudioPresentation.actionBarButtons(paused: false, viewOnly: false, drawingEnabled: false, connected: true, galleryCount: 1)
        #expect(empty.first { $0.kind == .gallery }?.disabled == true)
        #expect(nonEmpty.first { $0.kind == .gallery }?.disabled == false)
    }

    @Test("Home is never disabled, even when disconnected")
    func actionBarHomeAlwaysEnabled() {
        let buttons = StudioPresentation.actionBarButtons(paused: false, viewOnly: false, drawingEnabled: false, connected: false, galleryCount: 0)
        #expect(buttons.first { $0.kind == .home }?.disabled == false)
    }

    @Test("Draw/Nudge/Pause disable when disconnected")
    func actionBarDisconnectedDisablesConnectivityGatedButtons() {
        let buttons = StudioPresentation.actionBarButtons(paused: false, viewOnly: false, drawingEnabled: false, connected: false, galleryCount: 1)
        #expect(buttons.first { $0.kind == .draw }?.disabled == true)
        #expect(buttons.first { $0.kind == .nudge }?.disabled == true)
        #expect(buttons.first { $0.kind == .pause }?.disabled == true)
    }

    @Test("Draw button reflects drawingEnabled as its active state")
    func actionBarDrawActiveState() {
        let on = StudioPresentation.actionBarButtons(paused: false, viewOnly: false, drawingEnabled: true, connected: true, galleryCount: 0)
        let off = StudioPresentation.actionBarButtons(paused: false, viewOnly: false, drawingEnabled: false, connected: true, galleryCount: 0)
        #expect(on.first { $0.kind == .draw }?.active == true)
        #expect(off.first { $0.kind == .draw }?.active == false)
    }

    // MARK: - Tool presentation (ux spec §6.1)

    @Test("Known tool names resolve to their exact TOOL_DISPLAY_NAMES copy")
    func toolDisplayNames() {
        let expectations: [(String, String)] = [
            ("draw_paths", "drawing paths"),
            ("generate_svg", "generating SVG"),
            ("view_canvas", "viewing canvas"),
            ("critique_canvas", "critiquing canvas"),
            ("mark_piece_done", "marking done"),
            ("imagine", "imagining"),
            ("sign_canvas", "signing"),
            ("name_piece", "naming piece"),
        ]
        for (name, expected) in expectations {
            #expect(StudioPresentation.presentation(forToolName: name).displayName == expected)
        }
    }

    @Test("Unknown or nil tool names fall back to a generic presentation")
    func toolDisplayNameFallback() {
        #expect(StudioPresentation.presentation(forToolName: "not_a_real_tool").displayName == "Running code")
        #expect(StudioPresentation.presentation(forToolName: nil).displayName == "Running code")
    }

    @Test("isInProgress matches messages with an ellipsis that haven't completed")
    func isInProgressDetection() {
        #expect(StudioPresentation.isInProgress(messageText: "Drawing 3 paths...") == true)
        #expect(StudioPresentation.isInProgress(messageText: "Drew 3 paths") == false)
        #expect(StudioPresentation.isInProgress(messageText: "SVG generated") == false)
        #expect(StudioPresentation.isInProgress(messageText: "Marking done...") == true)
    }

    @Test("currentTool walks messages backward for the most recent code_execution tool")
    func currentToolFindsMostRecent() {
        let messages = [
            makeMessage(type: .codeExecution, toolName: "view_canvas"),
            makeMessage(type: .thinking),
            makeMessage(type: .codeExecution, toolName: "draw_paths"),
        ]
        #expect(StudioPresentation.currentTool(messages: messages) == "draw_paths")
    }

    @Test("currentTool is nil with no code_execution messages")
    func currentToolNilWithoutCodeExecution() {
        #expect(StudioPresentation.currentTool(messages: [makeMessage(type: .thinking)]) == nil)
        #expect(StudioPresentation.currentTool(messages: []) == nil)
    }

    // MARK: - LiveStatus visibility and content (ux spec §6.1)

    @Test("LiveStatus is hidden when idle with no buffered content")
    func liveStatusHiddenWhenIdleAndEmpty() {
        var state = StudioState()
        state.paused = false
        #expect(StudioPresentation.liveStatus(for: state) == nil)
    }

    @Test("LiveStatus shows Paused with no trailing ellipsis")
    func liveStatusPaused() {
        var state = StudioState()
        state.paused = true
        let display = StudioPresentation.liveStatus(for: state)
        #expect(display?.label == "Paused")
        #expect(display?.isActive == false)
    }

    @Test("LiveStatus shows revealed thinking text while words are on stage")
    func liveStatusThinkingText() {
        var state = StudioState()
        state.paused = false
        state.performance.onStage = .words(id: "w1", text: "Hello there world")
        state.performance.revealedText = "Hello there"
        state.performance.wordIndex = 2
        let display = StudioPresentation.liveStatus(for: state)
        #expect(display?.label == "Thinking")
        #expect(display?.isActive == true)
        if case let .thinking(text, isBuffering)? = display?.body {
            #expect(text == "Hello there")
            #expect(isBuffering == true)
        } else {
            Issue.record("expected .thinking body")
        }
    }

    @Test("LiveStatus's event bubble uses the tool's display name and completed icon")
    func liveStatusEventBubble() {
        var state = StudioState()
        state.paused = false
        let message = makeMessage(type: .codeExecution, text: "Drew 3 paths", toolName: "draw_paths")
        state.performance.onStage = .event(id: "e1", message: message)
        let display = StudioPresentation.liveStatus(for: state)
        #expect(display?.label == "drawing paths")
        if case let .event(icon, colorKey, text)? = display?.body {
            #expect(icon == StudioPresentation.presentation(forToolName: "draw_paths").icon)
            #expect(colorKey == .primary)
            #expect(text == "Drew 3 paths")
        } else {
            Issue.record("expected .event body")
        }
    }

    @Test("LiveStatus falls back to the current tool's display name while executing without an event")
    func liveStatusExecutingUsesCurrentTool() {
        var state = StudioState()
        state.paused = false
        state.messages = [makeMessage(type: .codeExecution, text: "Generating SVG...", toolName: "generate_svg")]
        // hasUnmatchedCodeExecutionStarted requires a `.started` status with no matching `.completed`.
        state.messages[0].status = .started
        let display = StudioPresentation.liveStatus(for: state)
        #expect(display?.label == "generating SVG")
    }

    // MARK: - Formatting helpers

    @Test("code(fromToolInput:) extracts the code field")
    func codeFromToolInput() {
        let input = JSONValue.object(["code": .string("print(1)")])
        #expect(StudioPresentation.code(fromToolInput: input) == "print(1)")
    }

    @Test("code(fromToolInput:) is nil without a code field")
    func codeFromToolInputMissing() {
        #expect(StudioPresentation.code(fromToolInput: .object(["other": .string("x")])) == nil)
        #expect(StudioPresentation.code(fromToolInput: nil) == nil)
    }

    @Test("formatTime produces a non-empty local time string")
    func formatTimeIsNonEmpty() {
        let formatted = StudioPresentation.formatTime(epochMilliseconds: 1_700_000_000_000)
        #expect(!formatted.isEmpty)
    }

    // MARK: - Fixtures

    private func makeMessage(
        type: AgentMessageType,
        text: String = "",
        toolName: String? = nil
    ) -> AgentMessage {
        AgentMessage(
            id: UUID().uuidString,
            type: type,
            text: text,
            timestamp: 0,
            metadata: toolName.map { AgentMessageMetadata(toolName: $0) }
        )
    }
}
