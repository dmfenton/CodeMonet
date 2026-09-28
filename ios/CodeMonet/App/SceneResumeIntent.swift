/// The app may background again while foreground auth and socket work is
/// still awaiting. Retain the original running intent, but reject work from
/// an older scene transition or an ended authentication session.
struct SceneResumeIntent {
    private(set) var generation = 0
    private(set) var wasRunning = false

    mutating func background(wasPaused: Bool) -> Bool {
        generation += 1
        wasRunning = wasRunning || !wasPaused
        return wasRunning
    }

    mutating func foreground() -> Int {
        generation += 1
        return generation
    }

    mutating func confirmedRunning() { wasRunning = false }

    func shouldResume(
        generation: Int,
        sceneActive: Bool,
        signedIn: Bool,
        sameSession: Bool
    ) -> Bool {
        self.generation == generation && sceneActive && signedIn && sameSession && wasRunning
    }
}
