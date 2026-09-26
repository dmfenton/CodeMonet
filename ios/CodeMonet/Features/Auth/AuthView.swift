import FentonDesignSystem
import FentonMobileCore
import SwiftUI

/// Magic-link sign-in (ux spec §3). Full-screen, centered column, generous
/// horizontal padding. There is no OTP/code-entry step in the current app —
/// sign-in is: enter email -> tap send -> backend emails a magic link ->
/// the user opens it on-device -> `RootView`'s deep link handling exchanges
/// the code and this screen is replaced by the main app.
struct AuthView: View {
    @Environment(AppEnvironment.self) private var environment
    @Environment(\.fentonTheme) private var fentonTheme
    @Environment(\.colorScheme) private var colorScheme

    @State private var email = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var didSendLink = false

    @ScaledMetric(relativeTo: .largeTitle) private var titleSize: CGFloat = 32
    @ScaledMetric(relativeTo: .body) private var subtitleSize: CGFloat = 18
    @ScaledMetric(relativeTo: .body) private var fieldFontSize: CGFloat = 16

    private var palette: FentonTheme.Palette { fentonTheme.palette(for: colorScheme) }

    /// A local validation/server error takes precedence; otherwise a
    /// magic-link deep-link failure carried in from `RootView` (ux spec §3's
    /// `magicLinkError` prop) is shown until the user edits the field, and
    /// finally `AuthService`'s own post-exchange identity-mapping failure
    /// (`AppAuthState.error`), which `RootView` also routes to this screen.
    private var displayedError: String? {
        errorMessage ?? environment.magicLinkError ?? authStateErrorMessage
    }

    private var authStateErrorMessage: String? {
        if case let .error(message) = environment.auth.state { return message }
        return nil
    }

    var body: some View {
        VStack(spacing: 24) {
            header
            form
                .frame(maxWidth: 420) // native improvement #7: don't stretch full-width on iPad.
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(palette.surface.ignoresSafeArea())
        .sensoryFeedback(.success, trigger: didSendLink)
    }

    private var header: some View {
        VStack(spacing: 4) {
            Text("Code Monet")
                .font(.system(size: titleSize, weight: .bold))
                .foregroundStyle(palette.text)
            Text("Sign in with email")
                .font(.system(size: subtitleSize))
                .foregroundStyle(palette.secondaryText)
        }
        .padding(.bottom, 24)
    }

    private var form: some View {
        VStack(spacing: 12) {
            emailField

            if let displayedError {
                MessageBox(text: displayedError, tint: CodeMonetDesignSystem.Extra.error)
            }
            if didSendLink {
                MessageBox(text: "Check your email for a sign-in link", tint: palette.accent)
            }

            submitButton
        }
    }

    private var emailField: some View {
        TextField("Email", text: $email)
            .textContentType(.emailAddress)
            .keyboardType(.emailAddress)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .disabled(isSubmitting)
            .font(.system(size: fieldFontSize))
            .padding(.horizontal, 12)
            .frame(minHeight: 48)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(palette.divider, lineWidth: 1)
            )
            .accessibilityIdentifier("email-input")
            .accessibilityLabel("Email address")
            .onChange(of: email) { _, _ in handleEmailEdited() }
    }

    private var submitButton: some View {
        Button {
            submit()
        } label: {
            Group {
                if isSubmitting {
                    ProgressView()
                        .tint(.white)
                } else {
                    Text("Send Magic Link")
                        .font(.system(size: fieldFontSize, weight: .semibold))
                }
            }
            .frame(maxWidth: .infinity, minHeight: 48)
        }
        .background(palette.accent)
        .foregroundStyle(.white)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .opacity(isSubmitting ? 0.6 : 1)
        .disabled(isSubmitting)
        .accessibilityIdentifier("auth-submit-button")
        .accessibilityLabel(isSubmitting ? "Sending" : "Send Magic Link")
    }

    /// Ux spec §3: "Any user interaction with the email field clears the
    /// parent-level magic-link error too", and typing again after a
    /// successful send clears the success message.
    private func handleEmailEdited() {
        errorMessage = nil
        environment.magicLinkError = nil
        didSendLink = false
    }

    private func submit() {
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = "Email is required"
            return
        }
        errorMessage = nil
        environment.magicLinkError = nil
        isSubmitting = true
        Task {
            defer { isSubmitting = false }
            do {
                try await environment.auth.requestMagicLink(email: trimmed)
                didSendLink = true
            } catch {
                didSendLink = false
                errorMessage = AuthRequestErrorPresentation.message(for: error)
            }
        }
    }
}

/// Ux spec §3's error copy mapping for a failed `requestMagicLink` call — a
/// pure function (no I/O) so it's unit-testable. RN reads a `result.error`
/// string straight off a non-throwing API response; `AuthenticationController`
/// throws instead, so a transport-layer failure maps to "Network error" and
/// everything else server/API-side falls back to the documented default.
enum AuthRequestErrorPresentation {
    static func message(for error: Error) -> String {
        guard let apiError = error as? MobileAPIError else {
            return "An unexpected error occurred"
        }
        switch apiError {
        case .transport:
            return "Network error"
        case .unauthorized, .http, .notFound, .invalidURL, .invalidResponse, .decoding:
            return "Authentication failed"
        }
    }
}

/// The error/success tinted boxes (ux spec §3): `colors.X + '20'` (~12%
/// alpha) background, `colors.X` text.
private struct MessageBox: View {
    let text: String
    let tint: Color

    var body: some View {
        Text(text)
            .font(.system(size: 14))
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(RoundedRectangle(cornerRadius: 12).fill(tint.opacity(0.12)))
    }
}
