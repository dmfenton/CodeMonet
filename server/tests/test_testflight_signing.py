from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_testflight_delegates_signing_to_platform_action() -> None:
    workflow = (ROOT / ".github/workflows/testflight.yml").read_text()
    fastfile = (ROOT / "ios/fastlane/Fastfile").read_text()

    # Public repo: the private platform action is used from the lock-pinned checkout.
    assert (
        workflow.count("uses: ./vendor/platform.dmfenton.net/.github/actions/isolated-ios-signing")
        == 2
    )
    assert "dmfenton/platform.dmfenton.net/.github/actions" not in workflow
    assert "apple-actions/import-codesign-certs" not in workflow
    assert "security create-keychain" not in workflow
    assert 'ENV.fetch("FENTON_IOS_SIGNER_PATH")' in fastfile
    assert "skip_codesigning: true" in fastfile
    assert "skip_package_ipa: true" in fastfile


def test_testflight_signing_names_the_dedicated_ci_account() -> None:
    """The action refuses self-hosted signing unless told the account it runs as."""
    workflow = (ROOT / ".github/workflows/testflight.yml").read_text()

    assert "runs-on: [self-hosted, codemonet-ios, laptop, dedicated-signing]" in workflow
    assert workflow.count("expected-user: fenton-ci") == 1
