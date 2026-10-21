import AppMetricaCore
import FirebaseAnalytics

enum Tracker {
    static func log(_ name: String) {
        AppMetrica.reportEvent(name: name)
        Analytics.logEvent(name, parameters: nil)
    }
}
