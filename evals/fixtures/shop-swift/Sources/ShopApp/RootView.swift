import SwiftUI

struct RootView: View {
    var body: some View {
        TabView {
            CatalogView()
                .tabItem { Label("Каталог", systemImage: "bag") }
            ConsultationView()
                .tabItem { Label("Консультации", systemImage: "bubble.left.and.bubble.right") }
            SubscriptionView()
                .tabItem { Label("Клуб", systemImage: "star") }
            SettingsView()
                .tabItem { Label("Настройки", systemImage: "gear") }
        }
        .tint(Theme.accent)
    }
}
