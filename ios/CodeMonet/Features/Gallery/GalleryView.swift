import SwiftUI

/// Gallery grid (ux spec §8). Functioning-but-simplified placeholder — a
/// plain list of piece numbers, no thumbnails yet (thumbnail loading is the
/// home+gallery+new-canvas UI work package's job, via
/// `CodeMonetRESTClient.thumbnailData`).
struct GalleryView: View {
    @Environment(AppEnvironment.self) private var environment

    var body: some View {
        NavigationStack {
            List(environment.studio.state.gallery.reversed(), id: \.id) { entry in
                Button {
                    environment.studio.send(.loadCanvas(pieceNumber: entry.pieceNumber))
                    environment.navigation.screen = .studio
                } label: {
                    Text(entry.title ?? "#\(entry.pieceNumber)")
                }
            }
            .overlay {
                if environment.studio.state.gallery.isEmpty {
                    ContentUnavailableView(
                        "No saved artwork yet",
                        systemImage: "photo.on.rectangle",
                        description: Text("Finish a piece to see it here.")
                    )
                }
            }
            .navigationTitle("Gallery")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { environment.navigation.closeGallery() }
                }
            }
        }
    }
}
