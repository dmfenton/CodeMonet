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

/// A paint run streaming its performance (`painting_live`, `init.painting_live`):
/// `{asset_base}performance.bin` grows while the program paints. Same
/// asset contract as `PaintingVersionRef` minus `version` — the run becomes
/// a version only once the server records it (`painting_version` with the
/// same `asset_base`).
public struct PaintingLiveRef: Codable, Equatable, Sendable {
    public var pieceNumber: Int
    /// API-relative, ends in `/` (same as `PaintingVersionRef.assetBase`).
    public var assetBase: String
    public var imageWidth: Int
    public var imageHeight: Int

    public init(pieceNumber: Int, assetBase: String, imageWidth: Int, imageHeight: Int) {
        self.pieceNumber = pieceNumber
        self.assetBase = assetBase
        self.imageWidth = imageWidth
        self.imageHeight = imageHeight
    }

    enum CodingKeys: String, CodingKey {
        case pieceNumber = "piece_number"
        case assetBase = "asset_base"
        case imageWidth = "image_width"
        case imageHeight = "image_height"
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
    /// Total paint ops the render produced (the picture's mark count as
    /// of this version), when the server reports it.
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

/// Decodes a JSON array element by element, skipping elements that fail to
/// decode, so one malformed entry (e.g. in an additive `versions` list)
/// can't fail the whole payload.
struct LossyArray<Element: Decodable>: Decodable {
    var elements: [Element]

    init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        var elements: [Element] = []
        while !container.isAtEnd {
            if let element = try? container.decode(Element.self) {
                elements.append(element)
            } else {
                // Consume the bad element so decoding moves on.
                _ = try container.decode(JSONValue.self)
            }
        }
        self.elements = elements
    }
}
