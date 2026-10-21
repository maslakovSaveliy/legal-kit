import SwiftUI
import AppMetricaCore
import FirebaseCore

@main
struct ShopApp: App {
    init() {
        FirebaseApp.configure()
        if let config = AppMetricaConfiguration(apiKey: "00000000-0000-0000-0000-000000000000") {
            AppMetrica.activate(with: config)
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
