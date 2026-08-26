from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_testflight_delegates_signing_to_platform_action() -> None:
    workflow = (ROOT / ".github/workflows/testflight.yml").read_text()
    fastfile = (ROOT / "app/fastlane/Fastfile").read_text()

    assert workflow.count("isolated-ios-signing@") == 2
    assert "apple-actions/import-codesign-certs" not in workflow
    assert "security create-keychain" not in workflow
    assert 'ENV.fetch("FENTON_IOS_SIGNER_PATH")' in fastfile
    assert "skip_codesigning: true" in fastfile
    assert "skip_package_ipa: true" in fastfile
