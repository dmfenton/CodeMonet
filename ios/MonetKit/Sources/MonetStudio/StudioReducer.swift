import MonetProtocol

/// The pure `(State, Event) -> State` transition function for `StudioState`
/// (protocol-state spec §5). No I/O, no clocks, no randomness — every
/// non-deterministic input (message ids, timestamps) is threaded in through
/// the event's associated values by the caller. Safe to unit test with plain
/// value equality; safe to replay fixtures against.
public enum StudioReducer {
    public static func reduce(_ state: StudioState, _ event: StudioEvent) -> StudioState {
        var s = state
        switch event {
        // MARK: Strokes (§5.1)
        case let .addStroke(path):
            s.strokes.append(path)
        case let .setStrokes(strokes):
            s.strokes = strokes
        case let .startStroke(point):
            s.currentStroke = [point]
        case let .addPoint(point):
            s.currentStroke.append(point)
        case .endStroke:
            s.currentStroke = []

        // MARK: Thinking / messages (§5.2)
        case let .setThinking(text):
            s.thinking = text
        case let .appendThinking(text):
            s.thinking += text
        case let .archiveThinking(messageID, timestamp):
            let trimmed = s.thinking.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty {
                let message = AgentMessage(
                    id: messageID, type: .thinking, text: s.thinking, timestamp: timestamp, version: s.workingVersion
                )
                s.messages = Self.boundedPush(s.messages, message, limit: StudioState.maxMessages)
                s.notebook = Self.notebookPush(s.notebook, message)
            }
            s.thinking = ""
        case let .addMessage(message):
            var stamped = message
            stamped.version = s.workingVersion
            s.messages = Self.boundedPush(s.messages, stamped, limit: StudioState.maxMessages)
            s.notebook = Self.notebookPush(s.notebook, stamped)
        case .clearMessages:
            s.messages = []
            s.notebook = []

        // MARK: Metadata (§5.3)
        case .toggleDrawing:
            s.drawingEnabled.toggle()
        case let .setCanvasSize(width, height):
            s.canvasWidth = width
            s.canvasHeight = height
        case let .setPieceNumber(number):
            s.pieceNumber = number
        case let .setGallery(gallery):
            s.gallery = gallery
        case let .setStyle(style, config):
            s.drawingStyle = style
            s.styleConfig = config
        case let .setPaused(paused):
            s.paused = paused
        case let .setIteration(current, max):
            s.currentIteration = current
            s.maxIterations = max
        case .resetTurn:
            // Dead action in the source app today (never dispatched) — kept
            // for parity per protocol-state spec §5.3.
            s.thinking = ""
            s.currentIteration = 0
        case let .setTitle(title):
            s.title = title
        case let .setPrompt(prompt):
            s.prompt = prompt
        case let .setTurnActive(active):
            s.turnActive = active
        case let .pieceTitle(pieceNumber, title):
            let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
            if pieceNumber == s.pieceNumber, !trimmed.isEmpty { s.title = trimmed }

        // MARK: Canvas lifecycle (§5.4)
        case .clear:
            s.performance = PerformanceState()
            s.strokes = []
            s.currentStroke = []
            s.viewingPiece = nil
            s.viewingImageURL = nil
            s.savedCanvas = nil
            s.messages = []
            s.notebook = []
            s.thinking = ""
            // `clear` and `new_canvas` (routed through this same event, see
            // `MessageRouter`) both reset painting to none (program-painting
            // spec §1.3).
            s.painting = PaintingState()
            s.versions = []
            s.title = nil
            s.prompt = nil
        case let .loadCanvas(payload):
            // ⚑ savedCanvas snapshot rule (protocol-state spec §5.4): only
            // snapshot when we're currently on the live canvas
            // (`viewingPiece == nil`). Navigating from one gallery piece
            // straight to another must NOT overwrite the original live-canvas
            // snapshot, or "back to studio" would restore the wrong thing.
            if s.viewingPiece == nil {
                s.savedCanvas = SavedCanvas(
                    strokes: s.strokes,
                    canvasWidth: s.canvasWidth,
                    canvasHeight: s.canvasHeight,
                    pieceNumber: s.pieceNumber,
                    drawingStyle: s.drawingStyle,
                    styleConfig: s.styleConfig,
                    // Settle any in-flight reveal before snapshotting — an
                    // interrupted reveal must come back finished, not
                    // resumed (program-painting spec §4.1 `LOAD_CANVAS`).
                    painting: settlePainting(s.painting)
                )
            }
            // Live painting is hidden for the whole duration of gallery
            // viewing, not just on first entry — navigating gallery piece
            // to gallery piece must not resurrect it either.
            s.painting = PaintingState()
            s.performance = PerformanceState()
            s.strokes = payload.strokes
            s.currentStroke = []
            s.viewingPiece = payload.pieceNumber
            // `.raster` (program painting, no vector strokes): the piece's
            // content is its final image, not `payload.strokes` (empty).
            s.viewingImageURL = payload.format == .raster ? payload.imageURL : nil
            s.canvasWidth = payload.canvasWidth
            s.canvasHeight = payload.canvasHeight
            // ⚑ drawingStyle = action.drawingStyle ?? state.drawingStyle
            // (keep current if omitted — unlike INIT, this is NOT a reset to
            // a fixed default). styleConfig = action.styleConfig ??
            // (action.drawingStyle ? getStyleConfig(action.drawingStyle) :
            // state.styleConfig) — i.e. if a style *name* arrives without a
            // config object, derive the config from the name; if neither
            // arrives, keep the current config untouched.
            if let config = payload.styleConfig {
                s.styleConfig = config
            } else if let style = payload.drawingStyle {
                s.styleConfig = Self.defaultConfig(for: style)
            }
            s.drawingStyle = payload.drawingStyle ?? s.drawingStyle
        case .clearViewing:
            if s.viewingPiece != nil {
                if let saved = s.savedCanvas {
                    s.strokes = saved.strokes
                    s.canvasWidth = saved.canvasWidth
                    s.canvasHeight = saved.canvasHeight
                    s.pieceNumber = saved.pieceNumber
                    s.drawingStyle = saved.drawingStyle
                    s.styleConfig = saved.styleConfig
                    // Restored verbatim — already settled by `.loadCanvas`,
                    // so an interrupted reveal comes back finished, not
                    // resumed (program-painting spec §4.1 `CLEAR_VIEWING`).
                    s.painting = saved.painting
                    s.savedCanvas = nil
                }
                s.viewingPiece = nil
                s.viewingImageURL = nil
            }
        case let .initialize(payload):
            Self.applyInitialize(payload, to: &s)

        // MARK: Performance / animation pipeline (§5.5)
        case let .enqueueWords(text):
            if case let .words(id, existing)? = s.performance.buffer.last,
               Self.wordCount(existing) < Self.maxWordsPerChunk {
                s.performance.buffer[s.performance.buffer.count - 1] = .words(id: id, text: existing + text)
            } else {
                s.performance.buffer.append(.words(id: Self.syntheticID(prefix: "words", seed: s.performance.buffer.count), text: text))
            }
        case let .enqueueEvent(message):
            s.performance.buffer.append(.event(id: message.id, message: message))
        case let .enqueueStrokes(strokes):
            let id = strokes.first.map { "strokes_\($0.batchId)" } ?? Self.syntheticID(prefix: "strokes", seed: s.performance.buffer.count)
            s.performance.buffer.append(.strokes(id: id, strokes: strokes))
        case .advanceStage:
            guard s.performance.onStage == nil, !s.performance.buffer.isEmpty else { break }
            let next = s.performance.buffer.removeFirst()
            s.performance.onStage = next
            s.performance.wordIndex = 0
            s.performance.strokeIndex = 0
            s.performance.strokeProgress = 0
            if case .strokes = next {
                s.performance.agentStroke = []
                s.performance.agentStrokeStyle = nil
            } else {
                s.performance.revealedText = ""
            }
            s.performance.travelTarget = nil
        case .revealWord:
            if case let .words(_, text) = s.performance.onStage {
                let words = text.split(whereSeparator: { $0.isWhitespace }).map(String.init)
                let newIndex = min(s.performance.wordIndex + 1, words.count)
                s.performance.wordIndex = newIndex
                s.performance.revealedText = words.prefix(newIndex).joined(separator: " ")
            }
        case let .strokeProgressBatch(points, style):
            guard !points.isEmpty else { break }
            if s.performance.agentStroke.isEmpty, let style {
                s.performance.agentStrokeStyle = style
            }
            s.performance.agentStroke.append(contentsOf: points)
            if let last = points.last {
                if let current = s.performance.penPosition {
                    if Self.distance(current, last) >= 2.0 {
                        s.performance.penPosition = last
                    }
                } else {
                    s.performance.penPosition = last
                }
            }
            s.performance.penDown = true
        case .strokeComplete:
            guard case let .strokes(_, strokes) = s.performance.onStage,
                  s.performance.strokeIndex < strokes.count
            else { break }
            s.strokes.append(strokes[s.performance.strokeIndex].path)
            s.performance.strokeIndex += 1
            s.performance.strokeProgress = 0
            s.performance.agentStroke = []
            s.performance.agentStrokeStyle = nil
            s.performance.penDown = false
            s.performance.travelTarget = strokes[safe: s.performance.strokeIndex]?.points.first
        case let .penTravelBatch(points):
            guard let last = points.last else { break }
            s.performance.penPosition = last
            s.performance.penDown = false
        case .penTravelComplete:
            s.performance.travelTarget = nil
        case .stageComplete:
            if let onStage = s.performance.onStage {
                s.performance.history = Self.boundedPush(s.performance.history, onStage, limit: PerformanceState.maxHistory)
            }
            s.performance.onStage = nil
            s.performance.penPosition = nil
            s.performance.penDown = false
            s.performance.agentStroke = []
            s.performance.agentStrokeStyle = nil
            s.performance.travelTarget = nil
        case .clearPerformance:
            s.performance = PerformanceState()

        // MARK: Program painting (program-painting spec §4.1)
        case let .paintingVersion(incoming, stages, ops):
            Self.applyPaintingVersion(incoming, stages: stages, ops: ops, to: &s)
        case let .paintingPlaybackDone(assetBase):
            guard s.painting.playing?.assetBase == assetBase else { break }
            s.painting = settlePainting(s.painting)
        }
        return s
    }

    /// The `PAINTING_VERSION` guard chain (program-painting spec §4.1),
    /// factored out of `reduce` to keep that function's cyclomatic
    /// complexity in line with the rest of the file — this is a single
    /// reducer case, not a second entry point; it stays `private` and
    /// mutates `state` in place exactly as its call site would inline.
    private static func applyPaintingVersion(
        _ incoming: PaintingVersionRef,
        stages: [String],
        ops: Int?,
        to state: inout StudioState
    ) {
        // Guard 1: gallery guard — live updates never interrupt gallery
        // viewing.
        guard state.viewingPiece == nil else { return }
        // Guard 2: stale-piece guard — an out-of-order message about an
        // older piece.
        guard incoming.pieceNumber >= state.pieceNumber else { return }
        // Collapse any in-flight reveal into `base` first, then read it.
        let current = settlePainting(state.painting).base
        let samePiece = current?.pieceNumber == incoming.pieceNumber
        // Guard 3: duplicate/older-version guard.
        if samePiece, let current, incoming.version <= current.version { return }
        state.pieceNumber = max(state.pieceNumber, incoming.pieceNumber)
        state.painting = PaintingState(base: samePiece ? current : nil, playing: incoming)
        // Version history follows the same acceptance: a new piece starts a
        // fresh list; the same piece appends (replacing a same-numbered
        // entry, e.g. one seeded from `init` without stages/ops).
        let entry = PaintingVersionSummary(ref: incoming, stages: stages, ops: ops)
        var history = samePiece || current == nil ? state.versions : []
        history.removeAll { $0.version >= incoming.version }
        history.append(entry)
        state.versions = history
    }

    /// `INIT`. Reconnecting to the piece already on screen (same piece
    /// number, notebook non-empty — the web client's `samePiece` rule) keeps
    /// the notebook, merges the version history, and keeps a title/prompt the
    /// payload omits. A different piece resets all of it and seeds the
    /// notebook from the payload's prompt and monologue.
    private static func applyInitialize(_ payload: InitPayload, to s: inout StudioState) {
        let samePiece = !s.notebook.isEmpty && payload.pieceNumber == s.pieceNumber
        s.performance = PerformanceState()
        s.strokes = payload.strokes
        s.gallery = payload.gallery
        s.pieceNumber = payload.pieceNumber
        s.paused = payload.paused
        s.turnActive = payload.turnActive
        s.canvasWidth = payload.canvasWidth
        s.canvasHeight = payload.canvasHeight
        s.viewingPiece = nil
        s.viewingImageURL = nil
        s.savedCanvas = nil
        s.drawingStyle = payload.drawingStyle
        s.styleConfig = payload.styleConfig
        // The short status window restarts: a `started` whose `completed`
        // was lost with the old socket must not read as still running.
        s.messages = []
        s.thinking = ""
        s.currentStroke = []
        // Latest known version only, shown immediately with no reveal
        // animation — `INIT` never starts a `playing` reveal, no matter
        // how recent the version (program-painting spec §4.1 `INIT`,
        // §4.6's reconnect row).
        s.painting = PaintingState(base: payload.painting, playing: nil)
        if samePiece {
            s.versions = mergeVersions(s.versions, seedVersions(payload))
            s.title = payload.title ?? s.title
            s.prompt = payload.prompt ?? s.prompt
        } else {
            s.versions = seedVersions(payload)
            s.title = payload.title
            s.prompt = payload.prompt
            s.notebook = seedNotebook(payload, workingVersion: s.workingVersion)
        }
    }

    /// Union by version number, the incoming entry winning a tie.
    static func mergeVersions(_ existing: [PaintingVersionSummary], _ incoming: [PaintingVersionSummary]) -> [PaintingVersionSummary] {
        var byVersion = Dictionary(existing.map { ($0.version, $0) }, uniquingKeysWith: { _, last in last })
        for entry in incoming { byVersion[entry.version] = entry }
        return byVersion.values.sorted { $0.version < $1.version }
    }

    /// A fresh piece's notebook: its prompt (as the user's entry) and the
    /// agent's latest monologue, when the payload carries them.
    private static func seedNotebook(_ payload: InitPayload, workingVersion: Int) -> [AgentMessage] {
        var seeded: [AgentMessage] = []
        if let prompt = payload.prompt?.trimmingCharacters(in: .whitespacesAndNewlines), !prompt.isEmpty {
            seeded.append(AgentMessage(id: "init-prompt-\(payload.pieceNumber)", type: .userNudge, text: prompt, timestamp: 0))
        }
        let monologue = payload.monologue.trimmingCharacters(in: .whitespacesAndNewlines)
        if !monologue.isEmpty {
            seeded.append(AgentMessage(
                id: "init-monologue-\(payload.pieceNumber)", type: .thinking, text: monologue, timestamp: 0,
                version: workingVersion
            ))
        }
        return seeded
    }

    /// Appends to the notebook log, dropping the oldest messages while it
    /// holds more than `maxNotebookEntries` entries. A `completed`
    /// code_execution merges into its `started` line, so it doesn't count.
    static func notebookPush(_ log: [AgentMessage], _ message: AgentMessage) -> [AgentMessage] {
        var result = log
        result.append(message)
        var entries = result.reduce(0) { $0 + (countsAsEntry($1) ? 1 : 0) }
        var drop = 0
        while entries > StudioState.maxNotebookEntries, drop < result.count {
            if countsAsEntry(result[drop]) { entries -= 1 }
            drop += 1
        }
        // Don't leave a `completed` whose `started` was just dropped.
        while drop > 0, drop < result.count, !countsAsEntry(result[drop]) { drop += 1 }
        if drop > 0 { result.removeFirst(drop) }
        return result
    }

    private static func countsAsEntry(_ message: AgentMessage) -> Bool {
        !(message.type == .codeExecution && message.status == .completed)
    }

    /// `init`'s version history: the server's list when it sends one, else
    /// just the current version (if any) — the rest of this session's
    /// versions accumulate from live `painting_version` messages.
    private static func seedVersions(_ payload: InitPayload) -> [PaintingVersionSummary] {
        if !payload.paintingVersions.isEmpty {
            return payload.paintingVersions.sorted { $0.version < $1.version }
        }
        return payload.painting.map { [PaintingVersionSummary(ref: $0)] } ?? []
    }

    // MARK: - Helpers

    private static let maxWordsPerChunk = 25

    private static func wordCount(_ text: String) -> Int {
        text.split(whereSeparator: { $0.isWhitespace }).count
    }

    private static func distance(_ a: Point, _ b: Point) -> Double {
        (( a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y)).squareRoot()
    }

    private static func defaultConfig(for style: DrawingStyleType) -> DrawingStyleConfig {
        style == .paint ? .paint : .plotter
    }

    /// Deterministic placeholder id for a freshly-created buffer item when no
    /// natural id (e.g. a batch id) exists. Real apps may prefer to thread a
    /// generator in; kept simple here since buffer-item identity only needs
    /// to be unique within one session for SwiftUI `Identifiable` diffing.
    private static func syntheticID(prefix: String, seed: Int) -> String {
        "\(prefix)_\(seed)"
    }

    static func boundedPush<T>(_ array: [T], _ element: T, limit: Int) -> [T] {
        var result = array
        result.append(element)
        if result.count > limit {
            result.removeFirst(result.count - limit)
        }
        return result
    }
}

private extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
