import Foundation
import Testing
@testable import MonetNetworking

/// Pure-logic coverage for `StudioWebSocketClient`'s reconnect policy
/// (protocol-state spec §1.1-1.2, net-auth spec §9.1). `URLSessionWebSocketTask`
/// isn't practically fakeable without a real socket, so these target the
/// two `static` helpers the actor's reconnect loop is built on, which is
/// where the actual policy (as opposed to the transport plumbing) lives.
@Suite("StudioWebSocketClient reconnect policy")
struct StudioWebSocketClientReconnectPolicyTests {
    @Test("close code 4001 maps to authenticationFailed")
    func authFailureCloseCode() {
        #expect(StudioWebSocketClient.closeReason(rawCloseCode: 4001) == .authenticationFailed)
    }

    @Test("every other close code, and no code at all, maps to .other")
    func otherCloseCodes() {
        #expect(StudioWebSocketClient.closeReason(rawCloseCode: 4003) == .other(code: 4003))
        #expect(StudioWebSocketClient.closeReason(rawCloseCode: 1006) == .other(code: 1006))
        #expect(StudioWebSocketClient.closeReason(rawCloseCode: nil) == .other(code: nil))
    }

    @Test("backoff grows exponentially from the base, before hitting the cap")
    func backoffGrowsExponentially() {
        // jitter = 1 (max) isolates the *ceiling* of each attempt so the
        // exponential growth itself is asserted deterministically.
        #expect(StudioWebSocketClient.backoffDelay(attempt: 0, base: 3, cap: 30, jitter: 1) == 3)
        #expect(StudioWebSocketClient.backoffDelay(attempt: 1, base: 3, cap: 30, jitter: 1) == 6)
        #expect(StudioWebSocketClient.backoffDelay(attempt: 2, base: 3, cap: 30, jitter: 1) == 12)
        #expect(StudioWebSocketClient.backoffDelay(attempt: 3, base: 3, cap: 30, jitter: 1) == 24)
    }

    @Test("backoff never exceeds the configured cap, however large the attempt")
    func backoffRespectsCap() {
        #expect(StudioWebSocketClient.backoffDelay(attempt: 4, base: 3, cap: 30, jitter: 1) == 30)
        #expect(StudioWebSocketClient.backoffDelay(attempt: 10, base: 3, cap: 30, jitter: 1) == 30)
        #expect(StudioWebSocketClient.backoffDelay(attempt: 1000, base: 3, cap: 30, jitter: 1) == 30)
    }

    @Test("backoff is full-jitter: a jitter of 0 always yields 0 delay")
    func zeroJitterYieldsZeroDelay() {
        #expect(StudioWebSocketClient.backoffDelay(attempt: 0, base: 3, cap: 30, jitter: 0) == 0)
        #expect(StudioWebSocketClient.backoffDelay(attempt: 5, base: 3, cap: 30, jitter: 0) == 0)
    }

    @Test("backoff is always non-negative and within [0, cappedCeiling]")
    func backoffStaysInBounds() {
        for attempt in 0 ..< 8 {
            for jitterTenth in 0 ... 10 {
                let jitter = Double(jitterTenth) / 10
                let delay = StudioWebSocketClient.backoffDelay(attempt: attempt, base: 3, cap: 30, jitter: jitter)
                let ceiling = min(3 * pow(2, Double(attempt)), 30)
                #expect(delay >= 0)
                #expect(delay <= ceiling + 0.0001)
            }
        }
    }
}

/// A `Sleeping` stub that never actually waits — records every requested
/// delay so a test can assert on them without real-time waits or any
/// dependency on socket/network behavior (the actor-level reconnect loop
/// that would *use* this in production also opens a real
/// `URLSessionWebSocketTask`, which isn't practically fakeable — that
/// end-to-end path is covered by the e2e agent against a real server).
private actor RecordingSleeper: Sleeping {
    private(set) var requestedDelays: [TimeInterval] = []
    func sleep(seconds: TimeInterval) async {
        requestedDelays.append(seconds)
    }
}

@Suite("StudioWebSocketClient configuration")
struct StudioWebSocketClientConfigurationTests {
    @Test("reconnectAttempt starts, and resets, at 0 after connect()")
    func connectResetsAttemptCounter() async {
        // Loopback + an unused high port: `connect()` itself only opens the
        // task and returns (protocol-state spec §1.1: the WS handshake is
        // fire-and-forget from the client's side, actual accept/reject
        // happens async) — so this assertion is synchronous with `connect()`
        // returning and never depends on that background connection's
        // eventual (unrelated-to-this-test) outcome.
        let client = StudioWebSocketClient(
            baseURL: URL(string: "ws://127.0.0.1:65500")!,
            configuration: .init(reconnectInterval: 0.01, maxReconnectInterval: 1),
            sleeper: RecordingSleeper(),
            jitterSource: { 0 }
        )
        await client.connect(token: "t", traceID: nil)
        #expect(await client.reconnectAttempt == 0)
        await client.disconnect()
    }

    @Test("send without an open socket throws notConnected instead of silently dropping")
    func sendWithoutSocketThrows() async {
        let client = StudioWebSocketClient(
            baseURL: URL(string: "ws://127.0.0.1:65500")!,
            configuration: .init(reconnectInterval: 0.01, maxReconnectInterval: 1),
            sleeper: RecordingSleeper(),
            jitterSource: { 0 }
        )
        await #expect(throws: StudioWebSocketClient.SendError.notConnected) {
            try await client.send(.nudge(text: "hello"))
        }
    }
}
