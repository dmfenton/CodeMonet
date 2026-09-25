import FentonMobileCore
import Foundation

/// One client-side trace span, matching the `POST /traces` body shape
/// (net-auth spec §8.1). `traceId` is X-Ray-compatible:
/// `1-{8 hex unix-seconds}-{24 hex random}`.
public struct ClientSpan: Codable, Equatable, Sendable {
    public var traceId: String
    public var spanId: String
    public var parentSpanId: String?
    public var name: String
    public var startTime: Double
    public var endTime: Double?
    public var attributes: [String: String]
    public var status: String
    public var error: String?

    public init(
        traceId: String,
        spanId: String,
        parentSpanId: String? = nil,
        name: String,
        startTime: Double,
        endTime: Double? = nil,
        attributes: [String: String] = [:],
        status: String = "ok",
        error: String? = nil
    ) {
        self.traceId = traceId
        self.spanId = spanId
        self.parentSpanId = parentSpanId
        self.name = name
        self.startTime = startTime
        self.endTime = endTime
        self.attributes = attributes
        self.status = status
        self.error = error
    }
}

/// Buffers spans in memory and flushes them to `POST /traces`
/// (net-auth spec §8.1). Bounded (drops when full, never grows unbounded);
/// a failed flush re-buffers its spans (up to the cap) rather than losing
/// them. The app target calls `flush()` on a timer and on background
/// transition.
public actor TraceSpanBuffer {
    private var spans: [ClientSpan] = []
    private let capacity: Int
    private let api: MobileAPIClient

    public init(baseURL: URL, capacity: Int = 500, transport: any HTTPTransport = URLSession.shared) {
        api = MobileAPIClient(baseURL: baseURL, transport: transport)
        self.capacity = capacity
    }

    public func record(_ span: ClientSpan) {
        guard spans.count < capacity else { return }
        spans.append(span)
    }

    /// Generates a fresh X-Ray-compatible trace id for a new drawing session
    /// (net-auth spec §8.1 `newSession()`).
    public static func newTraceID(now: Date = Date()) -> String {
        let seconds = Int(now.timeIntervalSince1970)
        let hexSeconds = String(format: "%08x", seconds)
        let random = (0 ..< 24).map { _ in String("0123456789abcdef".randomElement()!) }.joined()
        return "1-\(hexSeconds)-\(random)"
    }

    @discardableResult
    public func flush() async -> Bool {
        guard !spans.isEmpty else { return true }
        let batch = spans
        spans.removeAll()
        do {
            struct Body: Encodable { let spans: [ClientSpan] }
            struct Response: Decodable { let received: Int }
            _ = try await api.send(path: "/traces", body: Body(spans: batch), response: Response.self)
            return true
        } catch {
            // Re-buffer (don't drop) up to capacity.
            let room = capacity - spans.count
            if room > 0 {
                spans.append(contentsOf: batch.prefix(room))
            }
            return false
        }
    }
}
