import MonetProtocol

/// The `--json` export shape `scripts/render-study.py` writes and the
/// `monet-render` CLI reads (performer-render spec §15.1). This is the
/// contract point between the Python tooling and the Swift parity lane —
/// changing field names/shapes here requires updating
/// `scripts/render-study.py` in the same change.
public struct RenderStudyDocument: Codable, Equatable, Sendable {
    public var width: Int
    public var height: Int
    public var style: DrawingStyleType
    public var paths: [Path]

    public init(width: Int, height: Int, style: DrawingStyleType, paths: [Path]) {
        self.width = width
        self.height = height
        self.style = style
        self.paths = paths
    }
}
