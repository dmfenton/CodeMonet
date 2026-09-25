// swift-tools-version: 5.10
import PackageDescription

/// MonetKit — the platform-independent core of the Code Monet iOS app.
///
/// Every target here builds and tests with plain `swift build` / `swift test`
/// on macOS — no simulator required. UIKit/SwiftUI-specific code does not
/// belong in this package; it lives in the `CodeMonet` Xcode app target,
/// which depends on MonetKit's products.
///
/// Module graph (also documented in ../ARCHITECTURE.md):
///   MonetProtocol   <- MonetStudio <- MonetPerformer
///   MonetProtocol   <- MonetRender
///   MonetProtocol   <- MonetNetworking
///   MonetRender, MonetProtocol <- monet-render (executable)
let package = Package(
    name: "MonetKit",
    platforms: [
        .iOS(.v17),
        .macOS(.v14),
    ],
    products: [
        .library(name: "MonetProtocol", targets: ["MonetProtocol"]),
        .library(name: "MonetStudio", targets: ["MonetStudio"]),
        .library(name: "MonetPerformer", targets: ["MonetPerformer"]),
        .library(name: "MonetRender", targets: ["MonetRender"]),
        .library(name: "MonetNetworking", targets: ["MonetNetworking"]),
        .executable(name: "monet-render", targets: ["monet-render"]),
    ],
    dependencies: [
        // The shared Fenton platform package. MonetNetworking builds its
        // REST client on top of FentonMobileCore.MobileAPIClient rather than
        // rolling its own HTTP plumbing — see net-auth spec §3, §6.
        .package(path: "../../vendor/platform.dmfenton.net/swift"),
    ],
    targets: [
        .target(name: "MonetProtocol"),
        .target(name: "MonetStudio", dependencies: ["MonetProtocol"]),
        .target(name: "MonetPerformer", dependencies: ["MonetProtocol", "MonetStudio"]),
        .target(name: "MonetRender", dependencies: ["MonetProtocol"]),
        .target(
            name: "MonetNetworking",
            dependencies: [
                "MonetProtocol",
                .product(name: "FentonMobileCore", package: "swift"),
            ]
        ),
        .executableTarget(
            name: "monet-render",
            dependencies: ["MonetRender", "MonetProtocol"]
        ),
        .testTarget(name: "MonetProtocolTests", dependencies: ["MonetProtocol"]),
        .testTarget(name: "MonetStudioTests", dependencies: ["MonetStudio", "MonetProtocol"]),
        .testTarget(name: "MonetPerformerTests", dependencies: ["MonetPerformer", "MonetStudio", "MonetProtocol"]),
        .testTarget(name: "MonetRenderTests", dependencies: ["MonetRender", "MonetProtocol"]),
        .testTarget(name: "MonetNetworkingTests", dependencies: ["MonetNetworking", "MonetProtocol"]),
    ]
)
