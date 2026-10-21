import SwiftUI
import StoreKit

struct SubscriptionView: View {
    @State private var product: Product?

    var body: some View {
        VStack(spacing: Theme.spacing) {
            Text("Клуб «ЛавкаДом»").font(.title)
            Text("Скидка 10% на все заказы и ранний доступ к новинкам — 199 ₽ в месяц. Подписка продлевается автоматически.")
            Button("Оформить подписку") {
                Task { _ = try? await product?.purchase() }
            }
        }
        .padding(Theme.spacing)
        .task { product = try? await Product.products(for: ["lavkadom_club_month"]).first }
    }
}
