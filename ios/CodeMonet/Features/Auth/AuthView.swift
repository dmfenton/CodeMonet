import SwiftUI

/// Magic-link sign-in (ux spec §3). A functioning-but-simplified placeholder:
/// real copy/spacing/testIDs per the spec are the auth-UI work package's job
/// to fill in; the contract other code depends on is just that this view
/// reads/writes `AppEnvironment.auth` and nothing else.
struct AuthView: View {
    @Environment(AppEnvironment.self) private var environment
    @State private var email = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var didSendLink = false

    var body: some View {
        VStack(spacing: 24) {
            VStack(spacing: 4) {
                Text("Code Monet")
                    .font(.system(size: 32, weight: .bold))
                Text("Sign in with email")
                    .font(.system(size: 18))
                    .foregroundStyle(.secondary)
            }

            VStack(spacing: 12) {
                TextField("Email", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .accessibilityIdentifier("email-input")
                    .accessibilityLabel("Email address")
                    .padding(12)
                    .background(RoundedRectangle(cornerRadius: 12).strokeBorder(Color(uiColor: .separator)))

                if let errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                }
                if didSendLink {
                    Text("Check your email for a sign-in link")
                }

                Button {
                    submit()
                } label: {
                    if isSubmitting {
                        ProgressView().tint(.white)
                    } else {
                        Text("Send Magic Link")
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 48)
                .background(Color.accentColor)
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .disabled(isSubmitting)
                .accessibilityIdentifier("auth-submit-button")
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func submit() {
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = "Email is required"
            return
        }
        errorMessage = nil
        isSubmitting = true
        Task {
            defer { isSubmitting = false }
            do {
                try await environment.auth.requestMagicLink(email: trimmed)
                didSendLink = true
            } catch {
                errorMessage = "Authentication failed"
            }
        }
    }
}
