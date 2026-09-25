import FentonMobileCore
import Foundation
import Testing
@testable import MonetNetworking

/// Counts every request it receives and always succeeds with `{"received": N}`.
private actor CountingTransport: HTTPTransport {
    private(set) var requestCount = 0
    private let shouldFail: Bool

    init(shouldFail: Bool = false) {
        self.shouldFail = shouldFail
    }

    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        requestCount += 1
        if shouldFail {
            throw MobileTransportFailure.connectionLost
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        return (#"{"received": 1}"#.data(using: .utf8)!, response)
    }
}

/// A `Sleeping` stub that never actually waits and counts how many times
/// it was asked to.
private actor CountingSleeper: Sleeping {
    private(set) var callCount = 0
    func sleep(seconds: TimeInterval) async {
        callCount += 1
    }
}

private func makeSpan(name: String = "test", traceId: String = "1-aaaaaaaa-bbbbbbbbbbbbbbbbbbbbbbbb") -> ClientSpan {
    ClientSpan(traceId: traceId, spanId: TraceSpanBuffer.newSpanID(), name: name, startTime: 0)
}

@Suite("TraceSpanBuffer")
struct TraceSpanBufferTests {
    @Test("newTraceID matches the X-Ray-compatible shape: 1-{8 hex}-{24 hex}")
    func traceIDFormat() {
        let id = TraceSpanBuffer.newTraceID(now: Date(timeIntervalSince1970: 0))
        let parts = id.split(separator: "-", omittingEmptySubsequences: false)
        #expect(parts.count == 3)
        #expect(parts[0] == "1")
        #expect(parts[1].count == 8)
        #expect(parts[2].count == 24)
        #expect(parts[1].allSatisfy { $0.isHexDigit })
        #expect(parts[2].allSatisfy { $0.isHexDigit })
    }

    @Test("newSpanID is 16 hex characters")
    func spanIDFormat() {
        let id = TraceSpanBuffer.newSpanID()
        #expect(id.count == 16)
        #expect(id.allSatisfy { $0.isHexDigit })
    }

    @Test("flush is a no-op (and reports success) when nothing is buffered")
    func flushNoopWhenEmpty() async {
        let transport = CountingTransport()
        let buffer = TraceSpanBuffer(baseURL: URL(string: "http://localhost:8000")!, transport: transport)
        let ok = await buffer.flush()
        #expect(ok)
        #expect(await transport.requestCount == 0)
    }

    @Test("flush posts every buffered span in one request, then clears the buffer")
    func flushSendsAndClears() async {
        let transport = CountingTransport()
        let buffer = TraceSpanBuffer(baseURL: URL(string: "http://localhost:8000")!, transport: transport)
        await buffer.record(makeSpan(name: "ws.connect"))
        await buffer.record(makeSpan(name: "ws.connected"))
        #expect(await buffer.bufferedCount == 2)
        let ok = await buffer.flush()
        #expect(ok)
        #expect(await transport.requestCount == 1)
        #expect(await buffer.bufferedCount == 0)
    }

    @Test("a full buffer drops new spans rather than growing unbounded")
    func capacityDropsExcess() async {
        let transport = CountingTransport()
        let buffer = TraceSpanBuffer(baseURL: URL(string: "http://localhost:8000")!, capacity: 3, transport: transport)
        for i in 0 ..< 10 {
            await buffer.record(makeSpan(name: "span-\(i)"))
        }
        #expect(await buffer.bufferedCount == 3)
    }

    @Test("a failed flush re-buffers its spans instead of losing them")
    func failedFlushReBuffers() async {
        let transport = CountingTransport(shouldFail: true)
        let buffer = TraceSpanBuffer(baseURL: URL(string: "http://localhost:8000")!, transport: transport)
        await buffer.record(makeSpan())
        await buffer.record(makeSpan())
        let ok = await buffer.flush()
        #expect(!ok)
        #expect(await buffer.bufferedCount == 2)
    }

    @Test("a failed flush re-buffers only up to capacity, never past it")
    func failedFlushReBuffersUpToCapacityOnly() async {
        let transport = CountingTransport(shouldFail: true)
        let buffer = TraceSpanBuffer(baseURL: URL(string: "http://localhost:8000")!, capacity: 2, transport: transport)
        await buffer.record(makeSpan())
        await buffer.record(makeSpan())
        _ = await buffer.flush()
        #expect(await buffer.bufferedCount == 2) // not 2 (re-buffered) + more
    }

    @Test("startAutoFlush drives a periodic flush without a real-time wait")
    func autoFlushTicks() async {
        let transport = CountingTransport()
        let sleeper = CountingSleeper()
        let buffer = TraceSpanBuffer(baseURL: URL(string: "http://localhost:8000")!, transport: transport, sleeper: sleeper)
        await buffer.record(makeSpan())
        await buffer.startAutoFlush(interval: 10)
        // The sleeper never actually waits, so the loop free-runs; give the
        // scheduler a few turns to let at least one tick land.
        for _ in 0 ..< 50 where await transport.requestCount == 0 {
            await Task.yield()
        }
        await buffer.stopAutoFlush()
        #expect(await transport.requestCount >= 1)
        #expect(await sleeper.callCount >= 1)
    }

    @Test("stopAutoFlush stops further ticks")
    func stopAutoFlushStops() async {
        let transport = CountingTransport()
        let sleeper = CountingSleeper()
        let buffer = TraceSpanBuffer(baseURL: URL(string: "http://localhost:8000")!, transport: transport, sleeper: sleeper)
        await buffer.startAutoFlush(interval: 10)
        for _ in 0 ..< 20 where await sleeper.callCount == 0 {
            await Task.yield()
        }
        await buffer.stopAutoFlush()
        let countAfterStop = await sleeper.callCount
        // Give the (now-cancelled) loop several more scheduler turns; the
        // count must not keep climbing.
        for _ in 0 ..< 20 {
            await Task.yield()
        }
        #expect(await sleeper.callCount == countAfterStop)
    }
}
