# Flutter

Mechanics for editing an existing Flutter app. The legal documents are hosted on the owner's website; the app links to them. The knowledge pack decides which forms need consent and which texts to show; this file shows the mechanics. Reuse the project's navigation, widgets, theme and localization. Add no UI package.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- `pubspec.yaml` with a `flutter:` section, `lib/main.dart`, `android/` and `ios/`. Check `environment.sdk` and the Flutter version (`.fvmrc`, `.tool-versions`).
- Navigation: `go_router` (`GoRouter(routes: [...])`), `auto_route`, `beamer`, or plain `MaterialApp(routes:)` / `onGenerateRoute`. Where the routes live: `lib/router.dart`, `lib/app/router/`, `lib/main.dart`.
- UI: `MaterialApp`/Material 3 (`ThemeData`, `ColorScheme`), `CupertinoApp`, a theme/tokens file (`lib/theme/`), shared widgets (`lib/widgets`, `lib/ui`).
- State: `provider`, `flutter_riverpod`, `flutter_bloc`, `get`, `mobx`: put consent state in the same kind of provider/cubit/controller.
- Forms: `Form` + `TextFormField`, `flutter_form_builder` (`FormBuilderCheckbox`), `reactive_forms`.
- i18n: `flutter_localizations` + `intl` + `l10n.yaml` + `lib/l10n/*.arb`; `easy_localization` (`assets/translations/*.json`); `slang`. None: strings inline.
- Analytics: `appmetrica_plugin`, `firebase_core` + `firebase_analytics`, `firebase_crashlytics`, `appsflyer_sdk`; find calls with `grep -rnE "AppMetrica|FirebaseAnalytics|logEvent" lib`. Check `android/app/src/main/AndroidManifest.xml` and `ios/Runner/Info.plist` for Firebase collection flags.
- Persistence: `shared_preferences`, `hive`, `flutter_secure_storage`. Backend: API client in `lib/data`/`lib/services`; a server in this repo is unusual.

## Legal pages
- Add a `DocumentsScreen` (Scaffold + ListView of `ListTile`s from the project's shared widgets) and register it: `GoRoute(path: '/documents', builder: (_, __) => const DocumentsScreen())` (or the router in use). Link it from the existing Settings/Profile/About screen.
- Rows open hosted URLs: Политика, Оферта, Возврат, Реквизиты. Keep the URLs in one constants file (`lib/config/legal_links.dart`), identical to the website footer and the store listing.
```dart
import 'package:url_launcher/url_launcher.dart';
Future<void> openDoc(String url) => launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
```
- Use `url_launcher` or `webview_flutter` if already in `pubspec.yaml`. If neither exists, `url_launcher` (first-party) may be added; mention it in the report. Nothing else.
- Store listing (owner action, list it in the report): privacy policy URL in App Store Connect and Google Play Console, plus the store privacy questionnaires.
- Make documents reachable on the registration/login screen as well.

## Consent checkbox in forms
- Unchecked by default (`initialValue: false`), a field of its own, separate from "accept the offer/terms". Label from l10n; the policy link is a separate `TextButton` that calls `openDoc`, so tapping it does not toggle the box.
- Submit stays enabled unless the knowledge pack says consent is required for that form. When required: validator error on the field, and `onPressed: consent ? submit : null` if the design disables the button; the API validates too.
```dart
FormField<bool>(
  initialValue: false,
  validator: (v) => (requiresConsent && v != true) ? l10n.consentRequired : null,
  builder: (state) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    CheckboxListTile(
      value: state.value ?? false, onChanged: state.didChange,
      controlAffinity: ListTileControlAffinity.leading, contentPadding: EdgeInsets.zero,
      title: Text(l10n.consentPdLabel)),
    if (state.hasError) Text(state.errorText!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
  ]),
)
```
- `flutter_form_builder`: `FormBuilderCheckbox(name: 'consentPd', initialValue: false, title: Text(...), validator: FormBuilderValidators.equal(true))` when required (needs the validators package already installed; verify the signature for its version).
- Send `consentPd` and `formId` in the request body.

## Analytics gated by consent
Nothing collects before the first decision; the choice is persisted and applied on every launch.
- Default off at build time. Android `AndroidManifest.xml` inside `<application>`: `<meta-data android:name="firebase_analytics_collection_enabled" android:value="false" />`. iOS `Info.plist`: `FIREBASE_ANALYTICS_COLLECTION_ENABLED` = `false` (verify the key against current Firebase docs).
Keep only the SDKs the project already uses (delete the imports below that it lacks); never add an SDK.
```dart
// lib/analytics/consent_service.dart
import 'package:appmetrica_plugin/appmetrica_plugin.dart';        // verify API against the installed version
import 'package:firebase_analytics/firebase_analytics.dart';
import 'package:shared_preferences/shared_preferences.dart';

typedef Choice = ({bool analytics, bool marketing});                // Dart 3 record

class ConsentService {
  static const consentVersion = '1';                                // bump when the consent texts change
  static bool _activated = false;

  /// null = never asked, or asked for an older text version
  static Future<Choice?> stored() async {
    final p = await SharedPreferences.getInstance();
    if (p.getString('legal_consent_version') != consentVersion) return null;
    return (analytics: p.getBool('legal_consent_analytics') ?? false, marketing: p.getBool('legal_consent_marketing') ?? false);
  }
  static Future<void> set({required bool analytics, required bool marketing}) async {
    final p = await SharedPreferences.getInstance();
    await p.setString('legal_consent_version', consentVersion);
    await p.setBool('legal_consent_analytics', analytics);
    await p.setBool('legal_consent_marketing', marketing);
    await apply((analytics: analytics, marketing: marketing));
  }
  static Future<void> apply(Choice? c) async {
    final on = c?.analytics == true;
    await FirebaseAnalytics.instance.setAnalyticsCollectionEnabled(on);
    if (on && !_activated) { await AppMetrica.activate(AppMetricaConfig(appMetricaApiKey)); _activated = true; }
    else if (_activated) await AppMetrica.setDataSendingEnabled(on);   // revoke, and a later re-grant in the same session; verify method name
    // advertising/attribution SDKs (AppsFlyer, Facebook SDK): start here only when c?.marketing == true
  }
}
```
- One rule everywhere: analytics SDKs (AppMetrica, Firebase Analytics) start only when `analytics` is true; advertising/attribution SDKs only when `marketing` is true.
- In `main()` after `WidgetsFlutterBinding.ensureInitialized()` and `Firebase.initializeApp()`: `await ConsentService.apply(await ConsentService.stored());`. Remove the old unconditional `AppMetrica.activate(...)` in `main()`; `AppMetrica.activateInBackground` is not a consent mechanism, do not use it as one.
- `setAnalyticsCollectionEnabled` persists across launches (Firebase documents this for the native SDKs; the Dart plugin mirrors that API: verify against the installed `firebase_analytics`).
- Revoke: Settings switches, one per category; turning one off saves the other category unchanged (`ConsentService.set(analytics: false, marketing: (await ConsentService.stored())?.marketing ?? false)`), and a "withdraw all" action sets both to false. Turning analytics back on in the same session re-enables sending. AppMetrica has no documented runtime deactivate (verify): `setDataSendingEnabled(false)` stops sending now, and the next launch skips activation.
- Guard the project's `track()` / `logEvent` wrapper with `stored()?.analytics`. Other SDKs from Detect: gate them in `apply` or list them in the report.

## Consent banner
- When `stored() == null`, show the project's existing bottom sheet / `MaterialBanner` / dialog widget with Accept all and Reject of equal size and style, texts from l10n, and a link to `DocumentsScreen`. Use `Theme.of(context)` tokens, no new package.
- Accept all sets `analytics` and `marketing`; Reject sets neither; a Settings view offers two separate switches (off by default) and Save.
- Wire it through the project's state tool (provider/cubit) so a Settings change closes it. After a `consentVersion` bump `stored()` returns `null`, so the banner returns and SDKs stay off until the new choice.
- Await `stored()` before the first frame decision (splash/loading state) so returning users never see a flash.

## Consent log (existing backend only)
- A Flutter repo rarely contains a backend. If the app already writes user data to a backend (REST API, Firestore, Supabase) through an existing client, ask the owner before adding a collection/table, and follow the append-only rule (columns `subject_id`, `created_at` UTC, `consent_version`, `text_sha256`, `channel`, `form_id`, `ip` and `user_agent` filled server-side, `action`). NEVER introduce a new database or BaaS for this.
- Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android` (`Platform.isIOS ? 'ios' : 'android'`). `subjectId`: user id when signed in; for anonymous users a UUID created only when a grant is logged. Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
- The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
- Own server in the repo (Dart `shelf`/`dart_frog` with an ORM): follow `nestjs.md` for the shape.
- Otherwise report the gap (consents live only on the device) and hand the owner the field list so the backend team can add `POST /consents`.

## Footer and links
No footer in an app. Link the four documents from `DocumentsScreen`, the sign-up/login screen, and next to each consent checkbox. If the About screen shows the version, add the About-screen owner block (template section 3.4, [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites)) from `.legal/answers.json`; never invent values.

## i18n
- gen-l10n: add keys to `lib/l10n/app_ru.arb` (check `l10n.yaml` for which file is the template) and `app_en.arb`, with `@key` descriptions; run `flutter gen-l10n`; use `AppLocalizations.of(context)!.consentPdLabel` (or the project's `context.l10n` extension). Placeholders/plurals use ICU syntax.
- easy_localization/slang: same keys in the existing `ru`/`en` files.
- RU strings and documents are authoritative. EN is a translation: add `translationNotice` and show it on the Documents screen when the locale is EN.
- No i18n in the project: keep strings in one constants file; do not add `intl` tooling.

## Verify and record state
- `flutter pub get`, `dart format --output=none --set-exit-if-changed lib test`, `flutter analyze`, `flutter test`, `flutter gen-l10n` (when ARB changed).
- `flutter build apk --debug` or `flutter build ios --no-codesign` are slow; run them only when the user agrees. Search check: no `AppMetrica.activate` or `setAnalyticsCollectionEnabled(true)` outside `ConsentService`.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
