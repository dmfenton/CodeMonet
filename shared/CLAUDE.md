# Shared Library - TypeScript Standards

Standards for the platform-agnostic shared library used by web/. (The native
iOS app has its own equivalent types and reducer in `ios/MonetKit` — see
`ios/ARCHITECTURE.md` — rather than consuming this package.)

## Purpose

This library contains the web app's canvas state machine and protocol types:

- Canvas state reducer
- WebSocket message handlers
- Type definitions
- Animation hooks

**Must build after changes:** `cd shared && npm run build`

## Type Safety

### No `any` Types

```typescript
// Bad
function process(data: any): any { ... }

// Good
function process(data: PendingStroke): Path { ... }
```

### Export Types from index.ts

All public types must be exported from `index.ts`:

```typescript
// index.ts
export type { Path, Point, PendingStroke } from './types';
```

## React Patterns

### Memoize Expensive Components

Use `React.memo()` for components that:

- Render in lists
- Have stable props but parent re-renders frequently

```typescript
// Wrap the component definition
const MessageBubble = React.memo(function MessageBubble({
  message,
  isNew,
}: Props): React.JSX.Element {
  ...
});
```

### Cleanup in useEffect

Always clean up:

- Timeouts
- Event listeners
- Refs that track state

```typescript
useEffect(() => {
  const timeoutId = setTimeout(() => {
    // ...
  }, 500);

  return () => {
    clearTimeout(timeoutId);
  };
}, [deps]);
```

### Track Unmount for Async Operations

For hooks that run async operations:

```typescript
export function useStrokeAnimation(...) {
  const unmountedRef = useRef(false);

  useEffect(() => {
    unmountedRef.current = false;
    return () => {
      unmountedRef.current = true;
    };
  }, []);

  const animate = useCallback(async () => {
    for (const item of items) {
      if (unmountedRef.current) break;  // Stop if unmounted
      await processItem(item);
    }
  }, []);
}
```

### Refs vs State

| Use Ref                                        | Use State                           |
| ---------------------------------------------- | ----------------------------------- |
| Mutable value that shouldn't trigger re-render | Value that should trigger re-render |
| Tracking "in progress" flags                   | UI-visible data                     |
| Storing timeouts/intervals                     | User-facing state                   |
| Previous value comparison                      | Form inputs                         |

```typescript
// Ref: doesn't need to re-render when changed
const animatingRef = useRef(false);

// State: UI depends on this value
const [isConnected, setIsConnected] = useState(false);
```

## Reducer Patterns

### Clear Related State Together

When an action affects multiple state fields, clear them together:

```typescript
case 'LOAD_CANVAS':
  return {
    ...state,
    strokes: action.strokes,
    currentStroke: [],     // Clear user stroke
    agentStroke: [],       // Clear agent stroke too!
    viewingPiece: action.pieceNumber,
  };
```

### Bounded Collections

Use `boundedPush` to prevent memory growth:

```typescript
case 'ADD_MESSAGE':
  return {
    ...state,
    messages: boundedPush(state.messages, action.message, MAX_MESSAGES),
  };
```

## Hook Patterns

### Stable Callbacks

Use `useCallback` with minimal dependencies:

```typescript
// Good - stable callback
const handleMessage = useCallback((msg: ServerMessage) => {
  dispatch(routeMessage(msg));
}, []); // dispatch is stable from useReducer
```

### Return Stable Objects

Memoize return objects to prevent consumer re-renders:

```typescript
// If returning an object, memoize it
return useMemo(
  () => ({
    handleAuthError,
    isRefreshing: isRefreshingRef.current,
  }),
  [handleAuthError]
);
```

## Testing

Shared library tests go in `web/src/test/` since shared/ doesn't have its own test setup. Test through the consuming web app.

## File Organization

```
shared/src/
├── index.ts           # All public exports
├── types.ts           # Type definitions
├── utils.ts           # Pure utility functions (formatTime, getCodeFromInput, bionic)
├── canvas/
│   ├── index.ts       # Canvas exports
│   └── reducer.ts     # State machine with performance model
├── hooks/
│   ├── index.ts       # Hook exports
│   ├── useCanvas.ts   # Canvas state and WebSocket connection
│   └── usePerformer.ts # Progressive reveal animation
├── utils/
│   ├── logForwarder.ts    # Browser console log forwarding
│   ├── strokeSmoothing.ts # Stroke interpolation algorithms
│   └── svgPath.ts         # SVG path conversion (pathToSvgD, pointsToSvgD)
└── websocket/
    └── handlers.ts    # Message routing
```

