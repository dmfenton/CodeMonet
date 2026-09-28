# Event Streaming Architecture

Documentation of the real-time event streaming system between server and clients.

## Overview

Code Monet uses WebSocket-based real-time streaming to synchronize agent state across clients. The architecture follows a unidirectional data flow:

```
Server (Python)          Shared Library (TS)        Clients (React/RN)
     │                         │                         │
     │   Pydantic Models       │                         │
     │  ──────────────────►    │   TypeScript Types      │
     │   (ServerMessage)       │  ──────────────────►    │
     │                         │   (ServerMessage)       │
     │                         │                         │
     │                         │   Message Handlers      │
     │                         │  ──────────────────►    │
     │                         │   (routeMessage)        │
     │                         │                         │
     │                         │   Canvas Reducer        │
     │                         │  ──────────────────►    │
     │                         │   (canvasReducer)       │
     │                         │                         │
     │                         │   Derived State         │
     │                         │  ──────────────────►    │
     │                         │   (deriveAgentStatus)   │
```

## Message Types

### Server → Client Messages (12 types)

| Type              | Model                   | Purpose                            |
| ----------------- | ----------------------- | ---------------------------------- |
| `init`            | `InitMessage`           | Initial state on WebSocket connect |
| `paused`          | `PausedMessage`         | Agent pause state change           |
| `thinking_delta`  | `ThinkingDeltaMessage`  | Streaming thinking text            |
| `iteration`       | `IterationMessage`      | Agent turn iteration (1-5)         |
| `code_execution`  | `CodeExecutionMessage`  | Tool execution start/complete      |
| `agent_strokes_ready`   | `AgentStrokesReadyMessage`   | Strokes available for fetch        |
| `human_stroke` | `HumanStrokeMessage` | Single stroke finalized            |
| `piece_state`     | `PieceStateMessage`     | Piece number and completion status |
| `clear`           | `ClearMessage`          | Canvas cleared                     |
| `new_canvas`      | `NewCanvasMessage`      | New canvas started                 |
| `load_canvas`     | `LoadCanvasMessage`     | Gallery piece loaded               |
| `gallery_update`  | `GalleryUpdateMessage`  | Gallery list changed               |
| `style_change`    | `StyleChangeMessage`    | Drawing style changed              |
| `error`           | `ErrorMessage`          | Error occurred                     |

### Client → Server Messages (7 types)

| Type         | Model                    | Purpose                                |
| ------------ | ------------------------ | -------------------------------------- |
| `stroke`     | `ClientStrokeMessage`    | Human drew a stroke                    |
| `nudge`      | `ClientNudgeMessage`     | User guidance text                     |
| `clear`      | `ClientControlMessage`   | Clear canvas request                   |
| `pause`      | `ClientControlMessage`   | Pause agent; interrupts a running turn |
| `resume`     | `ClientControlMessage`   | Resume agent (with optional direction) |
| `new_canvas` | `ClientNewCanvasMessage` | Start new artwork                      |
| `set_style`  | `ClientSetStyleMessage`  | Change drawing style                   |

A user `pause` stops the agent at once: the running turn is interrupted (a paint
run in progress is killed and its live stream dropped with `painting_live_failed`).
When the last client disconnects the agent is also paused, but the running turn is
left to finish, so a brief disconnect never cuts work short.

## State Management

### Shared Reducer (`shared/src/canvas/reducer.ts`)

The canvas reducer is the single source of truth for UI state:

```typescript
/**
 * Canvas state has two text representations:
 *   - thinking: Accumulates for archiving when iteration ends (legacy, used for history)
 *   - performance.revealedText: What's currently displayed (progressive animation)
 */
interface CanvasHookState {
  // Performance system (animation queue)
  performance: PerformanceState;

  // Strokes
  strokes: Path[]; // Completed strokes on canvas
  currentStroke: Point[]; // Human's in-progress stroke

  // Thinking text (legacy - used for loading history)
  thinking: string;

  // Messages
  messages: AgentMessage[]; // Agent thought/action stream

  // Canvas metadata
  pieceNumber: number; // Current piece ID
  viewingPiece: number | null; // Gallery piece being viewed
  drawingEnabled: boolean; // Human can draw
  gallery: SavedCanvas[]; // Gallery pieces
  paused: boolean; // Agent is paused
  currentIteration: number; // Current iteration (0-5)
  maxIterations: number; // Max iterations per piece (default 5)
  pendingStrokes: PendingStrokesInfo | null; // Strokes to fetch
  drawingStyle: DrawingStyleType; // plotter or paint
  styleConfig: DrawingStyleConfig; // Full style configuration
}

/**
 * Performance state manages the animation queue for progressive reveal.
 *
 * Data flow:
 *   Server message → ENQUEUE_* → buffer → ADVANCE_STAGE → onStage → STAGE_COMPLETE → history
 */
interface PerformanceState {
  buffer: PerformanceItem[];      // Items waiting to perform
  onStage: PerformanceItem | null; // Currently performing
  history: PerformanceItem[];     // Completed items

  // Progress tracking
  wordIndex: number;              // For words: current position
  strokeIndex: number;            // For strokes: current stroke
  strokeProgress: number;         // For strokes: 0-1 within stroke

  // Live display state
  revealedText: string;           // Progressive text reveal
  penPosition: Point | null;      // Cursor position
  penDown: boolean;               // Pen touching canvas
  agentStroke: Point[];           // In-progress stroke points
  agentStrokeStyle: StrokeStyle | null;
}
```

### Message Routing (`shared/src/websocket/handlers.ts`)

Messages are routed through handlers that dispatch actions:

```typescript
const handlers: Record<string, MessageHandler<ServerMessage>> = {
  init: handleInit,
  paused: handlePaused,
  thinking_delta: handleThinkingDelta,
  code_execution: handleCodeExecution,
  // ... 10 more handlers
};

export function routeMessage(message: ServerMessage, dispatch: DispatchFn): void {
  const handler = handlers[message.type];
  if (handler) {
    handler(message, dispatch);
  }
}
```

### Status Derivation (`deriveAgentStatus`)

Agent status is derived entirely from client-side state - the server only sends
`paused` state changes, not synthetic status broadcasts:

```typescript
export function deriveAgentStatus(state: CanvasHookState): AgentStatus {
  // Paused overrides everything
  if (state.paused) return 'paused';

  // Check for error in last message
  const lastMessage = state.messages[state.messages.length - 1];
  if (lastMessage?.type === 'error') return 'error';

  const perf = state.performance;

  // Check performance state for active items
  const hasWordsOnStage = perf.onStage?.type === 'words';
  const hasWordsInBuffer = perf.buffer.some((item) => item.type === 'words');
  const hasStrokesOnStage = perf.onStage?.type === 'strokes';
  const hasStrokesInBuffer = perf.buffer.some((item) => item.type === 'strokes');
  const hasEventOnStage = perf.onStage?.type === 'event';

  // Thinking = words being revealed or waiting
  if (hasWordsOnStage || hasWordsInBuffer || state.thinking) return 'thinking';

  // Executing = event on stage
  if (hasEventOnStage) return 'executing';

  // Any in-progress event blocks drawing and shows as executing (legacy check)
  if (hasInProgressEvents(state.messages)) return 'executing';

  // Drawing = strokes being animated or waiting
  if (hasStrokesOnStage || hasStrokesInBuffer) return 'drawing';

  // Pending strokes = drawing phase (legacy check)
  if (state.pendingStrokes !== null) return 'drawing';

  return 'idle';
}
```

**Status Priority (highest to lowest):**
1. `paused` - explicitly paused
2. `error` - last message is error
3. `thinking` - words in buffer/onStage OR thinking text
4. `executing` - code_execution started but not completed
5. `drawing` - strokes in buffer/onStage or pendingStrokes
6. `idle` - default

### In-Progress Event Detection (`hasInProgressEvents`)

Critical for sequencing UI transitions:

```typescript
export function hasInProgressEvents(messages: AgentMessage[]): boolean {
  return messages.some((msg) => {
    // Live streaming message
    if (msg.id === LIVE_MESSAGE_ID) return true;

    // Code execution without return_code
    if (msg.type === 'code_execution' && msg.metadata?.return_code === undefined) {
      return true;
    }

    return false;
  });
}
```

## Key Constants

```typescript
// Shared library constants
export const MAX_MESSAGES = 50; // Max messages in state
export const LIVE_MESSAGE_ID = 'live_thinking'; // Live stream message ID
export const MAX_ITERATIONS = 5; // Max agent turns per piece

// Status labels (for UI)
export const STATUS_LABELS: Record<AgentStatus, string> = {
  idle: 'Ready',
  thinking: 'Thinking',
  executing: 'Running Code',
  drawing: 'Drawing',
  paused: 'Paused',
  error: 'Error',
};
```

## Streaming Patterns

### Thinking Text Streaming

```
Server                          Client
  │                               │
  │ thinking_delta {text: "I"}    │
  ├──────────────────────────────►│ APPEND_LIVE_MESSAGE
  │                               │ (id: LIVE_MESSAGE_ID)
  │ thinking_delta {text: "'ll"}  │
  ├──────────────────────────────►│ APPEND_LIVE_MESSAGE
  │                               │
  │ thinking {text: "I'll..."}    │
  ├──────────────────────────────►│ FINALIZE_LIVE_MESSAGE
  │                               │ (assigns unique ID)
```

### Code Execution Flow

```
Server                          Client
  │                               │
  │ code_execution {              │
  │   execution_id: "abc",        │
  │   status: "started",          │
  │   tool_name: "draw_paths"     │
  │ }                             │
  ├──────────────────────────────►│ ADD_MESSAGE (or create)
  │                               │ hasInProgressEvents = true
  │                               │ status = "executing"
  │                               │
  │ code_execution {              │
  │   execution_id: "abc",        │
  │   status: "completed",        │
  │   return_code: 0              │
  │ }                             │
  ├──────────────────────────────►│ UPDATE_MESSAGE
  │                               │ hasInProgressEvents = false
```

### Stroke Animation Flow

```
Server                          Client
  │                               │
  │ agent_strokes_ready {count, piece_number}│
  ├──────────────────────────────►│ STROKES_READY
  │                               │ Validate piece_number matches current canvas
  │                               │ pendingStrokes = {count, batchId, pieceNumber}
  │                               │
  │           GET /strokes/pending│
  │◄──────────────────────────────┤ Fetch pre-interpolated
  │                               │
  │ {strokes, piece_number}           │
  ├──────────────────────────────►│ Animate at 60fps
  │                               │ ADD_STROKE per stroke
  │                               │
  │                               │ CLEAR_PENDING_STROKES
  │                               │ status = "idle" or "thinking"
```

**Cross-canvas protection**: `piece_number` ensures strokes are only rendered on the
canvas they belong to. When a new canvas starts, pending strokes are cleared on
the server, and the client reducer ignores agent_strokes_ready messages with mismatched
piece_number.

## Design Decisions

### Why Derive Status Instead of Broadcasting It

1. **Single source of truth** - Status is computed from observable state
2. **No stale data** - Can't have status=idle while code_execution is running
3. **Testable** - Pure function, easy to test edge cases
4. **Reduced message complexity** - Server only sends actual events, not synthetic status

### Why Use Execution IDs

1. **In-place updates** - Started message updated with completion
2. **Correlation** - Match start/complete for same execution
3. **Deduplication** - Prevent duplicate messages on reconnect

### Why Bounded Collections

1. **Memory safety** - `MAX_MESSAGES = 50` prevents unbounded growth
2. **Performance** - UI doesn't slow down with old messages
3. **Relevance** - Old messages aren't actionable

---

# Architecture Critique

## Strengths

### 1. Clean Type System

The dual type system (Pydantic on server, TypeScript on client) with matching shapes provides strong type safety across the stack. The `ServerMessage` union type ensures handlers exist for all message types.

### 2. Derived State Pattern

`deriveAgentStatus()` computing status from observable state is robust. It's impossible to have stale status because it's recomputed on every render.

### 3. Shared Library

Platform-agnostic code in `shared/` means the reducer and handlers are tested once and work identically on web, iOS, and Android.

### 4. Event-Driven Wake

The orchestrator uses `asyncio.Event` for wake-up instead of polling, reducing latency and CPU usage.

## Weaknesses

### 1. ~~Message Type Proliferation~~ (Resolved)

~~**18 message types** is too many.~~

**Update:** Consolidated to 12 message types:

- Merged `status`/`paused` → `paused` only (status derived client-side)
- Removed `thinking` (use `thinking_delta` with finalization)
- Merged `piece_count`/`piece_complete` → `piece_state`
- Removed legacy `pen` message

### 2. ~~Implicit vs Explicit Status~~ (Resolved)

~~Status derivation has edge cases with `serverStatus` fallback.~~

**Update:** Status is now derived entirely client-side from actual events:

- `thinking_delta` → thinking
- `code_execution(started)` → executing
- `agent_strokes_ready` → drawing
- `paused` message → paused

No more `serverStatus` fallback or dual sources of truth.

### 3. Dual Stroke Fetch Pattern (Medium)

Strokes use a two-phase approach:

1. Server sends `agent_strokes_ready` notification
2. Client fetches via REST `/strokes/pending`

This adds complexity vs just sending strokes in WebSocket. The rationale (keeping WS light) is valid but the REST endpoint is another failure point.

### 4. Gallery Data Shape Mismatch (Low)

`SavedCanvas` has `strokes: Path[]` but is often sent with `strokes: []` for efficiency. This violates the "make illegal states unrepresentable" principle.

```python
# Current: strokes is always present, sometimes empty
class SavedCanvas(BaseModel):
    strokes: list[Path] = []
    stroke_count: int | None = None  # Redundant with len(strokes)

# Better: separate types for list vs detail
class GalleryEntry(BaseModel):
    id: str
    stroke_count: int

class SavedCanvasDetail(GalleryEntry):
    strokes: list[Path]
```

### 5. Handler Dispatch Indirection (Low)

The routing pattern adds a layer of indirection:

```typescript
// Current
handlers[message.type](message, dispatch);

// Each handler calls dispatch multiple times:
export const handleNewCanvas = (message, dispatch) => {
  dispatch({ type: 'CLEAR' });
  dispatch({ type: 'CLEAR_MESSAGES' });
};
```

Multiple dispatches per message can cause multiple re-renders. Consider returning action arrays that are batched.

### 6. No Message Ordering Guarantees (Medium)

WebSocket messages can arrive out of order after reconnect. There's no sequence number or timestamp ordering.

```typescript
// If reconnect sends init + agent_strokes_ready, order matters
// Currently relies on server sending in correct order
```

### 7. Unused Infrastructure (Low)

- `executor.py` PenMessage system is never called
- `PathType.svg` exists but is underutilized

## Recommendations

### ~~High Priority~~ (Done)

1. ~~**Consolidate message types**~~ - ✅ Reduced from 18 to 12
2. **Add message sequence numbers** - Handle reconnection ordering
3. **Separate GalleryEntry from SavedCanvas** - Make illegal states unrepresentable

### Medium Priority

4. **Batch reducer dispatches** - Return action arrays from handlers
5. ~~**Consider explicit status**~~ - ✅ Now fully client-derived, no server status
6. **Remove unused code** - Clean up executor.py

### Low Priority

7. **Document message flow** - Sequence diagrams for complex flows
8. **Add message schema validation** - Runtime validation on receive
9. **Consider WebSocket backpressure** - Don't flood slow clients

## Conclusion

The architecture is solid for a real-time collaborative drawing app. The core state management (derived status, bounded collections, shared reducer) is well-designed and testable.

Recent consolidation efforts have reduced message types from 18 to 12 and eliminated synthetic status broadcasting. Status is now derived entirely client-side from actual events (`thinking_delta`, `code_execution`, `agent_strokes_ready`, `paused`).
