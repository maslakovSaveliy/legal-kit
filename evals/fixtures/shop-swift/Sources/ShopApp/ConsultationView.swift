import SwiftUI

struct ConsultationView: View {
    @State private var name = ""
    @State private var phone = ""
    @State private var question = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Консультация дизайнера интерьера, 1500 ₽") {
                    TextField("Имя", text: $name)
                    TextField("Телефон", text: $phone).keyboardType(.phonePad)
                    TextEditor(text: $question).frame(minHeight: 100)
                }
                Button("Записаться на консультацию") {
                    Tracker.log("consultation_requested")
                }
            }
            .navigationTitle("Консультации")
        }
    }
}
