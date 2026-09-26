import Foundation
@testable import MonetProtocol
@testable import MonetStudio
import Testing

@Suite("Notebook display rules")
struct NotebookTextTests {
    private func tool(_ id: String, _ name: String, version: Int = 1) -> NotebookEntry {
        NotebookEntry(id: id, version: version, kind: .tool(NotebookToolCall(toolName: name, inProgress: false)))
    }

    // MARK: - Housekeeping grouping

    @Test("consecutive housekeeping tools collapse into one line of distinct names in first-seen order")
    func groupsHousekeeping() {
        let entries = [
            tool("1", "Write"), tool("2", "Edit"), tool("3", "Bash"), tool("4", "Write"),
            tool("5", "paint"),
            tool("6", "ToolSearch"),
        ]
        let grouped = Notebook.grouped(entries)
        #expect(grouped.map(\.id) == ["1", "5", "6"])
        #expect(grouped[0].kind == .housekeeping(["write", "edit", "bash"]))
        #expect(NotebookText.housekeepingLine(["write", "edit", "bash"]) == "write · edit · bash")
        #expect(grouped[2].kind == .housekeeping(["toolsearch"]))
    }

    @Test("a thought or a new version breaks a housekeeping run; domain tools are never grouped")
    func runsBreak() {
        let thought = NotebookEntry(id: "t", version: 1, kind: .thought("hm"))
        let grouped = Notebook.grouped([tool("1", "Read"), thought, tool("2", "Read"), tool("3", "Read", version: 2)])
        #expect(grouped.count == 4)
        let domain = Notebook.grouped([tool("a", "view_canvas"), tool("b", "imagine")])
        #expect(domain.count == 2)
        #expect(NotebookToolCall(toolName: "critique_canvas", inProgress: false).isDomain)
        #expect(!NotebookToolCall(toolName: "TodoWrite", inProgress: false).isDomain)
    }

    // MARK: - Domain tool labels

    @Test("domain tools read as plain-language lines")
    func domainLabels() {
        func line(_ name: String, title: String? = nil) -> String {
            NotebookText.toolLine(NotebookToolCall(toolName: name, inProgress: false, title: title), strokes: nil)
        }
        #expect(line("view_canvas") == "looked at the canvas")
        #expect(line("imagine") == "imagined a reference")
        #expect(line("sign_canvas") == "signed the canvas")
        #expect(line("mark_piece_done") == "marked the piece done")
        #expect(line("name_piece", title: "Dusk") == "named it “Dusk”")
        let paint = NotebookToolCall(toolName: "paint", inProgress: false, durationMs: 13_000, producedVersion: 6)
        #expect(NotebookText.toolLine(paint, strokes: 3978) == "paint v6 · 3,978 strokes · 13.0s")
        #expect(NotebookText.toolLine(NotebookToolCall(toolName: "paint", inProgress: true), strokes: nil) == "paint…")
        #expect(NotebookText.toolLine(NotebookToolCall(toolName: "paint", inProgress: false, failed: true), strokes: 9) == "paint · failed")
        #expect(NotebookText.duration(milliseconds: 64_000) == "1m 04s")
    }

    @Test("name_piece's title is captured from the call's input")
    func namePieceTitleCaptured() {
        let input = JSONValue.object(["title": .string("Impression, Fog")])
        let started = AgentMessage(
            id: "s", type: .codeExecution, text: "", timestamp: 0, iteration: 1, status: .started,
            metadata: AgentMessageMetadata(toolName: "name_piece", toolInput: input), version: 1
        )
        var completed = started
        completed.id = "c"
        completed.status = .completed
        let entries = Notebook.entries(messages: [started, completed], liveThinking: "", versions: [], workingVersion: 1)
        guard case let .tool(call) = entries.first?.kind else {
            Issue.record("expected tool entry")
            return
        }
        #expect(NotebookText.toolLine(call, strokes: nil) == "named it “Impression, Fog”")
    }

    // MARK: - Critique

    @Test("critique drops the verdict line, FINDINGS header, and FINISH GATE tail; splits bullets")
    func critiqueParsing() {
        let text = """
        VERDICT: FAIL

        FINDINGS:
        - **Value structure (partial pass):** reads as three bands.
          Sky and water merge.
        - Harbour: asymmetrical.

        The boats carry the piece.

        FINISH GATE: do not call mark_piece_done until all pass.
        - never shown
        """
        let summary = CritiqueSummary(parsing: text)
        #expect(summary.verdict == .fail)
        #expect(summary.label == "critique · fail")
        #expect(summary.lines == [
            .bullet("**Value structure (partial pass):** reads as three bands. Sky and water merge.", level: 0),
            .bullet("Harbour: asymmetrical.", level: 0),
            .paragraph("The boats carry the piece."),
        ])
    }

    @Test("a bold PASS verdict is recognized; text without a verdict is kept whole")
    func critiqueVariants() {
        let pass = CritiqueSummary(parsing: "**VERDICT:** PASS\n**FINDINGS:** Strong edges.")
        #expect(pass.verdict == .pass)
        #expect(pass.label == "critique · pass")
        #expect(pass.lines == [.paragraph("Strong edges.")])
        let plain = CritiqueSummary(parsing: "Reflections are too literal.\nSoften the water.")
        #expect(plain.verdict == nil)
        #expect(plain.label == "critique")
        #expect(plain.lines == [.paragraph("Reflections are too literal. Soften the water.")])
    }

    // MARK: - Stage bar caption

    private func segments(revealing: Int?) -> [StageSegment] {
        let manifest = RevealManifest(width: 10, height: 10, keyframes: [
            "tone", "sky lay-in", "water lay-in", "harbor", "the boats", "the sun", "glaze", "final touches",
        ].map { RevealKeyframe(label: $0, image: "kf.jpg", ops: [.area(x0: 0, y0: 0, x1: 1, y1: 1)]) })
        return StageBar.segments(manifest: manifest, revealingKeyframe: revealing)
    }

    @Test("caption names the revealing stage, or the stage count and last stage when done")
    func stageCaption() {
        #expect(StageBar.caption(segments(revealing: 3)) == "stage 4 of 8 · harbor")
        #expect(StageBar.caption(segments(revealing: nil)) == "8 stages · final touches")
    }

    @Test("labels show only when every segment fits its full label")
    func labelsFit() {
        let eight = segments(revealing: nil)
        #expect(!StageBar.labelsFit(eight, totalWidth: 360, spacing: 3, characterWidth: 6.6))
        let manifest = RevealManifest(width: 10, height: 10, keyframes: ["sky", "sea"].map {
            RevealKeyframe(label: $0, image: "kf.jpg", ops: [.area(x0: 0, y0: 0, x1: 1, y1: 1)])
        })
        let two = StageBar.segments(manifest: manifest, revealingKeyframe: nil)
        #expect(StageBar.labelsFit(two, totalWidth: 360, spacing: 3, characterWidth: 6.6))
    }
}
