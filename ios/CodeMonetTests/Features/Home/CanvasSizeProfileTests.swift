@testable import CodeMonet
import Testing

@Suite("CanvasSizeProfiles")
struct CanvasSizeProfileTests {
    @Test("exact dimensions match the RN CANVAS_PROFILES table byte-for-byte")
    func exactDimensions() {
        #expect(CanvasSizeProfiles.standard == CanvasSizeProfile(id: "standard", label: "Standard", width: 800, height: 600))
        #expect(CanvasSizeProfiles.masthead == CanvasSizeProfile(id: "masthead", label: "Masthead", width: 1200, height: 420))
        #expect(CanvasSizeProfiles.square == CanvasSizeProfile(id: "square", label: "Square", width: 800, height: 800))
        #expect(CanvasSizeProfiles.portrait == CanvasSizeProfile(id: "portrait", label: "Portrait", width: 600, height: 900))
        #expect(CanvasSizeProfiles.wide == CanvasSizeProfile(id: "wide", label: "Wide", width: 1200, height: 600))
    }

    @Test("standard is first in display order and the default selection")
    func standardIsFirst() {
        #expect(CanvasSizeProfiles.all.first == CanvasSizeProfiles.standard)
        #expect(CanvasSizeProfiles.all.count == 5)
    }

    @Test("aspect labels reduce each size")
    func aspectLabels() {
        #expect(CanvasSizeProfiles.all.map(\.aspectLabel) == ["4:3", "20:7", "1:1", "2:3", "2:1"])
    }

    @Test("all ids are unique")
    func uniqueIDs() {
        let ids = Set(CanvasSizeProfiles.all.map(\.id))
        #expect(ids.count == CanvasSizeProfiles.all.count)
    }
}
