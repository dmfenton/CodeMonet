import SwiftUI

/// A one-tap starting direction under the Home composer, with the two
/// paint dabs its chip shows.
struct PromptIdea: Identifiable, Hashable {
    let text: String
    let dabs: [String]

    var id: String { text }

    static let all: [PromptIdea] = [
        PromptIdea(text: "lemons on a blue cloth", dabs: ["#f2c230", "#2a4fb8"]),
        PromptIdea(text: "a storm at sea, after Turner", dabs: ["#d9b45a", "#3d4a3c"]),
        PromptIdea(text: "a night garden", dabs: ["#243a5c", "#8fb37a"]),
        PromptIdea(text: "a Hockney pool at noon", dabs: ["#39a9d9", "#f07f5c"]),
        PromptIdea(text: "sunflowers in the rain", dabs: ["#e8b523", "#7d8f9c"]),
        PromptIdea(text: "a foggy harbor at first light", dabs: ["#9fb3b8", "#e0703a"]),
    ]
}
