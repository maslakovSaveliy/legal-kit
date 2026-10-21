# Swift (iOS: SwiftUI and UIKit)

Mechanics for editing an existing native iOS app. The legal documents are hosted on the owner's website; the app links to them. The knowledge pack decides which forms need consent and which texts to show; this file shows the mechanics. Reuse the project's views, theme and string catalogs. Add no UI package.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- `*.xcodeproj` / `*.xcworkspace`, `Package.swift`, `Podfile`. List schemes: `xcodebuild -list`. Edit existing source files; do not hand-edit `project.pbxproj` unless a new file must be added (then prefer the project's folder-reference/synchronized-group setup, which needs no pbxproj change; otherwise ask).
- SwiftUI: `@main struct ...: App`, `WindowGroup`, `NavigationStack`, `NavigationSplitView`. UIKit: `AppDelegate.swift`, `SceneDelegate.swift`, storyboards/xibs, `UINavigationController`, `UITableViewController`.
- Design: `Theme`/`Color` extensions, `Assets.xcassets` colors, shared view modifiers and components (`Views/Components`, `DesignSystem`).
- Analytics SDKs (SPM `Package.resolved`, `Podfile.lock`): `AppMetricaCore` / `AppMetricaCrashes` (older: `YandexMobileMetrica`), `FirebaseAnalytics` + `GoogleService-Info.plist`, `AppsFlyerFramework`. Find calls with `grep -rnE "AppMetrica|YMM|Analytics\.|FirebaseApp\.configure" --include=*.swift .`
- Persistence: `UserDefaults`, `@AppStorage`, Keychain wrappers. SwiftData/Core Data are local stores, not a backend.
- Backend: an API client (`URLSession` wrapper, Alamofire, a generated OpenAPI client). A server inside this repo is unusual (Vapor `Package.swift` with `vapor`).
- Localization: `Localizable.xcstrings` (String Catalog), or `*.lproj/Localizable.strings`.
- Native Android (Kotlin/Java) has no stack file: apply the same mechanics (Documents row, activation of AppMetrica/Firebase only after consent, `setAnalyticsCollectionEnabled`), and report it as "verify manually".

## Legal pages
- Add a Documents screen reachable from the existing Settings/Profile/About screen. SwiftUI: a `DocumentsView` with a `List`, pushed through the project's navigation (`NavigationLink` / `navigationDestination`). UIKit: a row in the settings table that pushes a `DocumentsViewController`.
- Rows open hosted URLs: Политика, Оферта, Возврат, Реквизиты. Keep URLs in one enum (`LegalLinks`), identical to the website footer and the store listing.
```swift
struct DocumentsView: View {
    var body: some View {
        List {
            Link("documents.privacy", destination: LegalLinks.privacy)   // LocalizedStringKey from the catalog
            Link("documents.offer", destination: LegalLinks.offer)
        }.navigationTitle("documents.title")
    }
}
```
- UIKit: `present(SFSafariViewController(url: url), animated: true)` (import `SafariServices`, part of the SDK) or `UIApplication.shared.open(url)`.
- Store listing (owner action, list it in the report): privacy policy URL in App Store Connect (App Information) and the App Privacy questionnaire.
- Make the documents reachable on the registration/login screen too.

## Consent checkbox in forms
- Unchecked by default (`@State private var consentPd = false`), a field of its own, separate from "accept the offer/terms". Label from the string catalog; the policy link is a separate `Link` so tapping it does not toggle the box.
- Submit stays enabled unless the knowledge pack says consent is required for that form. When required: `.disabled(requiresConsent && !consentPd)` on the button, plus API-side validation.
- iOS has no checkbox control: use the project's own component. If none exists:
```swift
struct ConsentCheckbox: View {
    @Binding var isOn: Bool
    let label: LocalizedStringKey
    var body: some View {
        Button { isOn.toggle() } label: {
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: isOn ? "checkmark.square.fill" : "square")
                Text(label).multilineTextAlignment(.leading)
            }
        }
        .buttonStyle(.plain)
        .accessibilityValue(isOn ? Text("a11y.checked") : Text("a11y.unchecked"))   // keys in the catalog
    }
}
```
- A `Toggle` from the existing design system is also acceptable. UIKit: a `UIButton` with `isSelected` toggling `checkmark.square.fill` / `square` SF Symbols, `accessibilityTraits` set.
- Send `consentPd` and `formId` in the request body.

## Analytics gated by consent
Nothing collects before the first decision; the choice is persisted and applied on every launch.
- Default off at build time: `Info.plist` key `FIREBASE_ANALYTICS_COLLECTION_ENABLED` = `NO` (verify against current Firebase docs). Do not start AppMetrica in `application(_:didFinishLaunchingWithOptions:)` or `App.init()` unconditionally.
Keep only the SDKs the project already uses (delete the imports below that it lacks); never add an SDK.
```swift
import AppMetricaCore            // verify module/API names against the installed SDK version
import FirebaseAnalytics

@MainActor   // required for the static mutable state under Swift 6 strict concurrency
enum AnalyticsConsent {
    static let version = "1"                         // bump when the consent texts change
    struct Choice { let analytics: Bool; let marketing: Bool }
    private static let defaults = UserDefaults.standard
    private static var activated = false

    /// nil = never asked, or asked for an older text version
    static var stored: Choice? {
        guard defaults.string(forKey: "legal.consent.version") == version else { return nil }
        return Choice(analytics: defaults.bool(forKey: "legal.consent.analytics"),
                      marketing: defaults.bool(forKey: "legal.consent.marketing"))
    }
    static func set(analytics: Bool, marketing: Bool) {
        defaults.set(version, forKey: "legal.consent.version")
        defaults.set(analytics, forKey: "legal.consent.analytics")
        defaults.set(marketing, forKey: "legal.consent.marketing")
        apply()
    }
    static func apply() {
        let on = stored?.analytics == true
        Analytics.setAnalyticsCollectionEnabled(on)
        if on, !activated, let config = AppMetricaConfiguration(apiKey: Secrets.appMetricaKey) {
            AppMetrica.activate(with: config); activated = true
        } else if activated {
            AppMetrica.setDataSendingEnabled(on)       // revoke, and a later re-grant in the same session; verify method name
        }
        // advertising/attribution SDKs (AppsFlyer, Facebook SDK): start here only when stored?.marketing == true
    }
}
```
- One rule everywhere: analytics SDKs (AppMetrica, Firebase Analytics) start only when `analytics` is true; advertising/attribution SDKs only when `marketing` is true.
- Call `AnalyticsConsent.apply()` once at launch, after `FirebaseApp.configure()`. Remove the old unconditional `AppMetrica.activate`.
- Revoke: Settings toggles, one per category; turning one off saves the other category unchanged (`AnalyticsConsent.set(analytics: false, marketing: AnalyticsConsent.stored?.marketing ?? false)`), and a "withdraw all" action sets both to false. Turning analytics back on in the same session re-enables sending. AppMetrica has no documented runtime deactivate (verify): `setDataSendingEnabled(false)` stops sending now, and the next launch skips activation. Guard the project's tracking helper with `AnalyticsConsent.stored?.analytics == true`.
- Other SDKs from Detect: gate in `apply()` or list them in the report. A system tracking-permission prompt (ATT) is a separate store mechanism, not a replacement for this consent.

## Consent banner
- When `AnalyticsConsent.stored == nil`, present the project's existing sheet/alert component (SwiftUI `.sheet` or `.fullScreenCover`, UIKit modal) with Accept all and Reject of equal size and style, texts from the catalog, and a link row to Documents. Use theme colors and fonts; no new package.
- Accept all sets `analytics` and `marketing`; Reject sets neither; a Settings view offers two separate toggles (off by default) and Save.
- After an `AnalyticsConsent.version` bump `stored` returns `nil`, so the banner returns and SDKs stay off until the new choice.
- Read the stored value synchronously (UserDefaults) so there is no flash.

## Consent log (existing backend only)
- Only if the repo itself contains the backend with an ORM (Vapor + Fluent): add a Fluent model with the fields below. NEVER introduce a new database or BaaS for the log.
- Backend elsewhere: after a grant or a revoke and after each consent-bearing submit (never after a first-time refusal), `POST /consents` through the existing API client with `{ subjectId, consentVersion, formId, channel: "ios", action }`, only once the owner confirms the endpoint. Server fills `created_at` (UTC), `ip`, `user_agent`, `text_sha256`. `subjectId`: user id when signed in; for anonymous users a UUID created only when a grant is logged (Keychain/UserDefaults). Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
- Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`. Columns, append-only: `subject_id`, `created_at`, `consent_version`, `text_sha256`, `channel`, `form_id`, `ip`, `user_agent`, `action`.
- The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
- No backend or endpoint: report the gap (consents live only on the device).

## Footer and links
No footer in an app. Link the four documents from the Documents screen, the sign-up/login screen, and next to each consent checkbox. If the About screen shows the version, add the About-screen owner block (template section 3.4, [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites)) from `.legal/answers.json`; never invent values.

## i18n
- String Catalog (`Localizable.xcstrings`, JSON): add keys with `ru` and `en` localizations; the source language is usually `ru`. Use `Text("consent.label")` or `String(localized: "consent.label")`. Prefer editing through Xcode when it is open; the file is plain JSON otherwise:
```json
"consent.label" : { "localizations" : {
  "ru" : { "stringUnit" : { "state" : "translated", "value" : "<text from the documents step>" } },
  "en" : { "stringUnit" : { "state" : "translated", "value" : "<English translation>" } } } }
```
- Legacy: add the same keys to `ru.lproj/Localizable.strings` and `en.lproj/Localizable.strings` (`"consent.label" = "...";`), use `NSLocalizedString`.
- RU strings and documents are authoritative. EN strings are translations; add `documents.translationNotice` and show it on the Documents screen when the language is EN.

## Verify and record state
- `xcodebuild -scheme <Scheme> -destination 'generic/platform=iOS Simulator' build` (take the scheme from `xcodebuild -list`); `swift build` / `swift test` for plain SPM packages; `swiftlint` only if `.swiftlint.yml` exists.
- Search check: `AppMetrica.activate` and `setAnalyticsCollectionEnabled(true)` appear only in `AnalyticsConsent`.
- If a simulator is available, launch on a fresh install and confirm the banner shows and no analytics call happens before Accept.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
