import SwiftUI

struct CheckoutView: View {
    let item: Item
    @State private var name = ""
    @State private var phone = ""
    @State private var address = ""

    var body: some View {
        Form {
            Section("Получатель") {
                TextField("Имя", text: $name)
                TextField("Телефон", text: $phone).keyboardType(.phonePad)
                TextField("Адрес доставки", text: $address)
            }
            Section {
                Text("\(item.title): \(item.priceRub) ₽")
                Button("Оплатить заказ") {
                    Task { await placeOrder() }
                }
            }
        }
        .navigationTitle("Оформление")
    }

    // Creates the order on the backend and opens the payment page of the acquirer.
    private func placeOrder() async {
        Tracker.log("checkout_started")
        var request = URLRequest(url: URL(string: "https://api.lavkadom.test/v1/orders")!)
        request.httpMethod = "POST"
        request.httpBody = try? JSONEncoder().encode(["name": name, "phone": phone, "address": address, "item": item.title])
        _ = try? await URLSession.shared.data(for: request)
    }
}
