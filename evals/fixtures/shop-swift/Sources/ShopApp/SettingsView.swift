import SwiftUI

struct SettingsView: View {
    @AppStorage("pushEnabled") private var pushEnabled = true

    var body: some View {
        NavigationStack {
            Form {
                Toggle("Уведомления о заказах и акциях", isOn: $pushEnabled)
                Text("Версия 2.1.0")
            }
            .navigationTitle("Настройки")
        }
    }
}
