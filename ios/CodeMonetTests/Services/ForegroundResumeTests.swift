@testable import CodeMonet
import Testing

@Suite("Foreground painter resume")
struct ForegroundResumeTests {
    @Test("a second background preserves running intent and invalidates the first foreground task")
    func rapidSceneTransitions() {
        var intent = SceneResumeIntent()
        let firstPause = intent.background(wasPaused: false)
        #expect(firstPause)
        let firstForeground = intent.foreground()
        let secondPause = intent.background(wasPaused: true)
        #expect(secondPause)
        #expect(!intent.shouldResume(generation: firstForeground, sceneActive: false, signedIn: true, sameSession: true))
        let secondForeground = intent.foreground()
        #expect(intent.shouldResume(generation: secondForeground, sceneActive: true, signedIn: true, sameSession: true))
        intent.confirmedRunning()
        #expect(!intent.shouldResume(generation: secondForeground, sceneActive: true, signedIn: true, sameSession: true))
    }

    @Test("a signed-out or replaced session cannot consume an old resume")
    func sessionChanges() {
        var intent = SceneResumeIntent()
        let shouldPause = intent.background(wasPaused: false)
        #expect(shouldPause)
        let generation = intent.foreground()
        #expect(!intent.shouldResume(generation: generation, sceneActive: true, signedIn: false, sameSession: true))
        #expect(!intent.shouldResume(generation: generation, sceneActive: true, signedIn: true, sameSession: false))
    }

    @Test("resume waits for init, survives send failure and reconnect, and ends on server acknowledgement")
    func reconnectAndAcknowledgement() throws {
        var resume = ForegroundResumeState()
        resume.request()
        resume.connected()
        let beforeInit = resume.beginSend()
        #expect(beforeInit == nil)
        resume.receivedInit()
        let firstAttempt = resume.beginSend()
        let first = try #require(firstAttempt)
        resume.willSend(first)
        resume.sendFailed(first)
        let retryWithoutInit = resume.finishSend(first)
        #expect(!retryWithoutInit) // send failed; retry on a new init
        #expect(resume.pending)
        resume.disconnected()
        resume.connected()
        resume.receivedInit()
        let secondAttempt = resume.beginSend()
        let second = try #require(secondAttempt)
        #expect(second != first)
        resume.willSend(second)
        resume.acknowledged()
        let retryAfterAck = resume.finishSend(second)
        #expect(!retryAfterAck)
        #expect(!resume.pending)
    }

    @Test("re-background cancels an in-flight resume and a later request retries after it")
    func cancelAndRetry() throws {
        var resume = ForegroundResumeState()
        resume.connected()
        resume.receivedInit()
        resume.request()
        let oldAttempt = resume.beginSend()
        let old = try #require(oldAttempt)
        resume.willSend(old)
        resume.cancel()
        #expect(!resume.isCurrent(old))
        resume.request()
        let duringSend = resume.beginSend()
        #expect(duringSend == nil)
        let shouldRetry = resume.finishSend(old)
        #expect(shouldRetry)
        let nextAttempt = resume.beginSend()
        let next = try #require(nextAttempt)
        #expect(next != old)
        resume.willSend(next)
        resume.acknowledged() // the old Resume's delayed paused:false
        #expect(resume.pending)
        resume.acknowledged() // the current Resume's paused:false
        #expect(!resume.pending)
        resume.cancel() // session teardown also cancels pending work
        resume.disconnected()
        let retryAfterReset = resume.finishSend(next)
        #expect(!retryAfterReset)
        #expect(!resume.pending)
    }
}
