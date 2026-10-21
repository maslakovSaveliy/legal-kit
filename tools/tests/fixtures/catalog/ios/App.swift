import SwiftUI
import StoreKit
import AppTrackingTransparency
import AuthenticationServices
import AppMetricaCore

@main
struct DemoApp: App {
    init() {
        if let configuration = AppMetricaConfiguration(apiKey: "00000000-0000-0000-0000-000000000000") {
            AppMetrica.activate(with: configuration)
        }
    }

    var body: some Scene {
        WindowGroup { LoginView() }
    }
}

struct LoginView: View {
    var body: some View {
        SignInWithAppleButton(.signIn, onRequest: { _ in }, onCompletion: { _ in })
            .onAppear { ATTrackingManager.requestTrackingAuthorization { _ in } }
    }
}
