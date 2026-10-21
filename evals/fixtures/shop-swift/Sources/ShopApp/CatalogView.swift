import SwiftUI

struct Item: Identifiable {
    let id = UUID()
    let title: String
    let priceRub: Int
}

struct CatalogView: View {
    private let items = [
        Item(title: "Ваза керамическая", priceRub: 2490),
        Item(title: "Плед шерстяной", priceRub: 3490),
        Item(title: "Набор подсвечников", priceRub: 1790),
    ]

    var body: some View {
        NavigationStack {
            List(items) { item in
                NavigationLink {
                    CheckoutView(item: item)
                } label: {
                    HStack {
                        Text(item.title)
                        Spacer()
                        Text("\(item.priceRub) ₽")
                    }
                }
            }
            .navigationTitle("Каталог")
        }
    }
}
