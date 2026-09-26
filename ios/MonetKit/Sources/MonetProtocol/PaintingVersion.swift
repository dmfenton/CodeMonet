import Foundation

/// Everything the client needs to locate one program-painting version's
/// assets: `piece_number`/`version` identify it, `asset_base` (always
/// ending in `/`, relative to the **API** base URL, not the WS URL) is
/// where its files live. Shared shape of `init.painting` and the
/// `painting_version` message minus `stages` — see program-painting spec
/// §3.2. Stored verbatim as `MonetStudio.PaintingState.base`/`.playing`.
public struct PaintingVersionRef: Codable, Equatable, Sendable {
    public var pieceNumber: Int
    public var version: Int
    /// Path-relative-to-API-base, always ends in `/`, e.g.
    /// `/painting-assets/<user_id>/<token>/`.
    public var assetBase: String
    public var imageWidth: Int
    public var imageHeight: Int

    public init(pieceNumber: Int, version: Int, assetBase: String, imageWidth: Int, imageHeight: Int) {
        self.pieceNumber = pieceNumber
        self.version = version
        self.assetBase = assetBase
        self.imageWidth = imageWidth
        self.imageHeight = imageHeight
    }

    enum CodingKeys: String, CodingKey {
        case pieceNumber = "piece_number"
        case version
        case assetBase = "asset_base"
        case imageWidth = "image_width"
        case imageHeight = "image_height"
    }
}

/// One brush-footprint reveal operation from `reveal.json` (program-painting
/// spec §3.3). Coordinates are **image pixels** — the manifest's
/// `width`x`height`, not the logical canvas size (typically `RENDER_SCALE =
/// 2` larger).
///
/// Wire shape is a heterogeneous JSON array with a leading string tag:
/// `["s", width, x0,y0, x1,y1, ...]` (1..N points; a single point is a dot,
/// not a degenerate line — draw it as a filled circle of radius
/// `width/2`, not a stroke) or `["a", x0,y0, x1,y1]`. `RevealOp` decodes
/// that shape directly rather than modeling it as `[Double]` + a separate
/// tag, so callers get a typed, already-validated value.
public enum RevealOp: Equatable, Sendable {
    /// `width` > 0, `points.count >= 1`. A single point renders as a filled
    /// circle of radius `width/2`; more than one point is a round-capped,
    /// round-joined polyline.
    case stroke(width: Double, points: [Point])
    /// Normalized on decode so `x0 < x1` and `y0 < y1` regardless of the
    /// wire's point order (program-painting spec §3.3, `parseRevealOp`).
    case area(x0: Double, y0: Double, x1: Double, y1: Double)
}

/// Thrown by `RevealOp`'s decoder for a malformed op — mirrors
/// `parseRevealOp`'s validation in `shared/src/renderer/reveal.ts` (point
/// count `>= 3` numbers and `(count - 1) % 2 == 0` for a stroke op; exactly
/// 4 numbers for an area op).
public enum RevealOpDecodingError: Error, Equatable, Sendable {
    case unknownTag(String)
    case malformedStroke(numberCount: Int)
    case malformedArea(numberCount: Int)
    case emptyOp
}

extension RevealOp: Codable {
    public init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        guard !container.isAtEnd else {
            throw RevealOpDecodingError.emptyOp
        }
        let tag = try container.decode(String.self)
        var numbers: [Double] = []
        while !container.isAtEnd {
            numbers.append(try container.decode(Double.self))
        }
        switch tag {
        case "s":
            // width + 1..N (x,y) pairs: numbers.count >= 3 and
            // (numbers.count - 1) is even (program-painting spec §3.3).
            guard numbers.count >= 3, (numbers.count - 1).isMultiple(of: 2), numbers[0] > 0 else {
                // Mirrors `parseRevealOp` (shared/src/renderer/reveal.ts),
                // which also rejects width <= 0 rather than decoding it.
                throw RevealOpDecodingError.malformedStroke(numberCount: numbers.count)
            }
            let width = numbers[0]
            var points: [Point] = []
            var index = 1
            while index + 1 < numbers.count {
                points.append(Point(x: numbers[index], y: numbers[index + 1]))
                index += 2
            }
            self = .stroke(width: width, points: points)
        case "a":
            guard numbers.count == 4 else {
                throw RevealOpDecodingError.malformedArea(numberCount: numbers.count)
            }
            self = .area(
                x0: min(numbers[0], numbers[2]),
                y0: min(numbers[1], numbers[3]),
                x1: max(numbers[0], numbers[2]),
                y1: max(numbers[1], numbers[3])
            )
        default:
            throw RevealOpDecodingError.unknownTag(tag)
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.unkeyedContainer()
        switch self {
        case let .stroke(width, points):
            try container.encode("s")
            try container.encode(width)
            for point in points {
                try container.encode(point.x)
                try container.encode(point.y)
            }
        case let .area(x0, y0, x1, y1):
            try container.encode("a")
            try container.encode(x0)
            try container.encode(y0)
            try container.encode(x1)
            try container.encode(y1)
        }
    }
}

/// One entry in `reveal.json`'s `keyframes` array (program-painting spec
/// §3.3). `image` is a filename relative to the version's `asset_base`
/// (e.g. `"kf_00.jpg"`), never a full URL.
public struct RevealKeyframe: Codable, Equatable, Sendable {
    public var label: String
    public var image: String
    public var ops: [RevealOp]

    public init(label: String, image: String, ops: [RevealOp]) {
        self.label = label
        self.image = image
        self.ops = ops
    }
}

/// The full `reveal.json` manifest fetched from a painting version's
/// `asset_base` (program-painting spec §3.3). `width`/`height` are image
/// pixels and match `RevealOp` coordinates — not necessarily equal to
/// `PaintingVersionRef.imageWidth/imageHeight`, though in practice they are
/// (both come from the same server-side export); a Swift port should read
/// them from the manifest itself rather than assume equality with the ref.
public struct RevealManifest: Codable, Equatable, Sendable {
    public var width: Int
    public var height: Int
    public var keyframes: [RevealKeyframe]

    public init(width: Int, height: Int, keyframes: [RevealKeyframe]) {
        self.width = width
        self.height = height
        self.keyframes = keyframes
    }
}

/// One entry of a piece's version history: `init.painting.versions` and the
/// gallery detail's `versions` (`GET /gallery/{n}/strokes`). Additive server
/// fields — every one but `version`/`asset_base` is optional on the wire so
/// a partial or older payload still decodes. The client also builds these
/// itself from live `painting_version` messages when the server sends no
/// history (a session-only version list).
public struct PaintingVersionSummary: Codable, Equatable, Sendable, Identifiable {
    public var version: Int
    /// Same contract as `PaintingVersionRef.assetBase`: API-relative, ends in `/`.
    public var assetBase: String
    public var imageWidth: Int
    public var imageHeight: Int
    /// `cv.stage(...)` labels, consecutive duplicates already collapsed
    /// server-side. Empty when unknown.
    public var stages: [String]
    /// Total reveal ops the render produced (`reveal.json` op count), when
    /// the server reports it.
    public var ops: Int?
    public var createdAt: String?

    public var id: Int { version }

    public init(
        version: Int,
        assetBase: String,
        imageWidth: Int,
        imageHeight: Int,
        stages: [String] = [],
        ops: Int? = nil,
        createdAt: String? = nil
    ) {
        self.version = version
        self.assetBase = assetBase
        self.imageWidth = imageWidth
        self.imageHeight = imageHeight
        self.stages = stages
        self.ops = ops
        self.createdAt = createdAt
    }

    /// A live `painting_version` (or `init.painting`) ref as a history entry.
    public init(ref: PaintingVersionRef, stages: [String] = [], ops: Int? = nil) {
        self.init(
            version: ref.version,
            assetBase: ref.assetBase,
            imageWidth: ref.imageWidth,
            imageHeight: ref.imageHeight,
            stages: stages,
            ops: ops
        )
    }

    /// The asset-locating ref for this entry, for fetching its files.
    public func ref(pieceNumber: Int) -> PaintingVersionRef {
        PaintingVersionRef(
            pieceNumber: pieceNumber,
            version: version,
            assetBase: assetBase,
            imageWidth: imageWidth,
            imageHeight: imageHeight
        )
    }

    enum CodingKeys: String, CodingKey {
        case version
        case assetBase = "asset_base"
        case imageWidth = "image_width"
        case imageHeight = "image_height"
        case stages, ops
        case createdAt = "created_at"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        version = try container.decode(Int.self, forKey: .version)
        assetBase = try container.decode(String.self, forKey: .assetBase)
        imageWidth = try container.decodeIfPresent(Int.self, forKey: .imageWidth) ?? 0
        imageHeight = try container.decodeIfPresent(Int.self, forKey: .imageHeight) ?? 0
        stages = try container.decodeIfPresent([String].self, forKey: .stages) ?? []
        ops = try container.decodeIfPresent(Int.self, forKey: .ops)
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
    }
}

public extension RevealManifest {
    /// Number of brush-stroke (`"s"`) ops across every keyframe — what the
    /// UI calls "strokes" when the server sends no `ops` count.
    var strokeOpCount: Int {
        keyframes.reduce(0) { total, keyframe in
            total + keyframe.ops.reduce(0) { count, op in
                if case .stroke = op { return count + 1 }
                return count
            }
        }
    }
}
