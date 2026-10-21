# React Native (Expo and bare)

Mechanics for editing an existing React Native app. The legal documents are hosted on the owner's website (see the web stack file for hosting them); the app links to them. The knowledge pack decides which forms need consent and which texts to show; this file shows the mechanics. Reuse the project's navigation, UI kit, form and i18n pieces. Add no UI library.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- Expo: `expo` in `package.json`, `app.json` or `app.config.ts`, `eas.json`. Bare: `react-native` plus `ios/` and `android/` folders (an Expo project with `ios/` is prebuilt: edit the JS side, do not hand-edit generated native files unless the project does).
- Navigation: `expo-router` (`app/` folder with `_layout.tsx`) or `@react-navigation/native` (`createNativeStackNavigator`, `src/navigation`, `src/screens`).
- UI kit: `react-native-paper`, `@rneui/themed`, `tamagui`, `nativewind`, `gluestack-ui`, `react-native-elements`, or a local `components/ui` folder with a theme/tokens file.
- Forms: `react-hook-form`, `formik`, plain `useState`.
- i18n: `i18next` + `react-i18next` (+ `expo-localization`), `react-intl`, `lingui`, `i18n-js`.
- Analytics SDKs: `@appmetrica/react-native-analytics`, `@react-native-firebase/analytics` (+ `firebase.json`), `react-native-appsflyer`, `react-native-fbsdk-next`, `@amplitude/analytics-react-native`; find calls with `grep -rnE "AppMetrica|analytics\(\)|getAnalytics|appsFlyer" src app App.tsx index.js`. Other auto-starting SDKs (Crashlytics, Sentry, ad SDKs) go into the report, not into this change, unless the knowledge pack says otherwise.
- Persistence: `@react-native-async-storage/async-storage`, `react-native-mmkv`. Backend: an API client in `src/api` (is the server in this repo?).

## Legal pages
- Add a "Documents" screen reachable from Settings/Profile/About: Expo Router `app/documents.tsx` (registered automatically; add a `<Stack.Screen options={{ title }}>` in `_layout.tsx` if siblings do); React Navigation `DocumentsScreen` plus a `Stack.Screen name="Documents"` and an entry in the param list type.
- The screen is a list of rows (the project's `List.Item`/`Pressable` row component) opening hosted URLs: Политика, Оферта, Возврат, Реквизиты. Keep the URLs in one constants file (`src/config/legal.ts`), identical to the website footer and the store listing.
```tsx
import { Linking } from 'react-native';
const open = (url: string) => Linking.openURL(url);   // or WebBrowser.openBrowserAsync(url) if expo-web-browser is already installed
```
- No bundled copies of the documents unless the project already bundles content; a stale copy is worse than a link. No in-app WebView dependency to add.
- Store listing (owner action, list it in the report): privacy policy URL in App Store Connect (App Information) and Google Play Console (App content), plus the store privacy questionnaires.
- Add an entry point on the first screen where data is collected (registration/login) so documents are reachable before submitting.

## Consent checkbox in forms
- Unchecked by default (`useState(false)`, `defaultValues: { consentPd: false }`), a field of its own, separate from "accept the offer/terms". Label from i18n; the policy link is a separate pressable text that opens the hosted document, not part of the label's toggle target.
- Submit stays enabled unless the knowledge pack says consent is required for that form. When required: `disabled={!consentPd}` on the button and server-side validation.
- Use the project's `Checkbox` (Paper: `<Checkbox.Item status={v ? 'checked' : 'unchecked'} onPress={() => set(!v)} />`; `@rneui`: `<CheckBox checked onPress />`). Without one, a core-only component:
```tsx
<Pressable accessibilityRole="checkbox" accessibilityState={{ checked }} onPress={() => onChange(!checked)}
  style={styles.row} hitSlop={8}>
  <View style={[styles.box, checked && styles.boxOn]}>{checked ? <Text>✓</Text> : null}</View>
  <Text style={styles.label}>{label}</Text>
</Pressable>
```
- With react-hook-form wrap it in `Controller` (`value`/`onChange` from `field`). Style from the existing theme tokens.
- Send `consentPd` and the `formId` with the request so the backend can check and log it.

## Analytics gated by consent
SDKs start nothing until the stored choice says so. Persist the choice, apply it on every launch. Keep only the SDKs the project already uses (delete the imports below that it lacks); never add an SDK.
```ts
// src/analytics/consent.ts
import AsyncStorage from '@react-native-async-storage/async-storage';
import AppMetrica from '@appmetrica/react-native-analytics';                 // default import; verify against the installed version
import { getAnalytics, setAnalyticsCollectionEnabled } from '@react-native-firebase/analytics';
export const CONSENT_VERSION = '1';   // bump when the consent texts change
const KEY = 'legal_consent'; let activated = false;
export type Consent = { v: string; analytics: boolean; marketing: boolean; at: string };
export async function loadConsent(): Promise<Consent | null> {   // null = never asked, or asked for an older text version
  try {
    const raw = await AsyncStorage.getItem(KEY); const c: Consent | null = raw ? JSON.parse(raw) : null;
    return c && c.v === CONSENT_VERSION ? c : null;
  } catch { return null; }
}
export async function saveConsent(c: Consent) { try { await AsyncStorage.setItem(KEY, JSON.stringify(c)); } catch {} await applyConsent(c); }
export async function applyConsent(c: Consent | null) {
  const on = !!c?.analytics;
  await setAnalyticsCollectionEnabled(getAnalytics(), on);
  if (on && !activated) { AppMetrica.activate({ apiKey: APPMETRICA_API_KEY }); activated = true; }
  else if (activated) AppMetrica.setDataSendingEnabled(on);                    // revoke, and a later re-grant in the same session; verify method name
}
```
- Call `loadConsent().then(applyConsent)` once in the root (`_layout.tsx`, `App.tsx`); delete the old unconditional `AppMetrica.activate(...)` at startup.
- Firebase: set `"react-native": { "analytics_auto_collection_enabled": false }` in `firebase.json` so nothing is collected before the first decision, then `setAnalyticsCollectionEnabled(getAnalytics(), true)` after consent (documented pattern). Older `@react-native-firebase` versions use the namespaced `analytics().setAnalyticsCollectionEnabled(on)`; match the installed major version. Expo: `firebase.json` is read at build time by the Firebase config plugins, so a dev-client rebuild is needed after changing it (verify against current docs).
- One rule everywhere: analytics SDKs (AppMetrica, Firebase Analytics, Amplitude) start only when `analytics` is true; advertising/attribution SDKs (AppsFlyer, Facebook SDK) only when `marketing` is true. Initialise them inside `applyConsent` the same way, or list them in the report as not gated.
- Revoke: Settings switches, one per category (Switch from the UI kit); turning one off saves the other category unchanged (`saveConsent({ ...c, analytics: false })` or `{ ...c, marketing: false }`), and a "withdraw all" action sets both to false. Turning analytics back on in the same session re-enables sending. AppMetrica has no documented runtime deactivate (verify): `setDataSendingEnabled(false)` stops sending now, and the next launch skips activation.
- Never call `logEvent`/`reportEvent` wrappers before the decision: guard the project's `track()` helper with the stored flag.

## Consent banner
- First launch with no stored choice (`loadConsent()` resolved to `null`): show the project's existing bottom sheet/`Modal`/`Banner` component with Accept and Reject of equal size and style, texts from `t('consent.*')`, and a link row to Documents. Style from theme tokens; no new component library.
- Accept all sets `analytics` and `marketing`; Reject sets neither; a Settings view offers two separate toggles (the UI kit's `Switch`/checkbox, off by default) and Save.
- Decision stored as `{ v: CONSENT_VERSION, analytics, marketing, at }`. After a `CONSENT_VERSION` bump `loadConsent()` returns `null`, so the banner returns and SDKs stay off until the new choice.
- Gate on `loadConsent` finishing (splash/`null` state) so the banner does not flash for returning users.

## Consent log (existing backend only)
- Only if this repo contains the backend with an ORM (rare in a mobile repo). Then follow `nestjs.md` / `nextjs.md` for the table and endpoint. NEVER introduce a new database or a BaaS for the log.
- Backend in another repo: the app only sends the event; add `api.post('/consents', { subjectId, consentVersion, formId, channel: Platform.OS, action })` (`Platform.OS` is `ios` or `android`) after a grant or a revoke and after each consent-bearing submit (never after a first-time refusal), once the owner confirms the endpoint exists. `subjectId`: user id when logged in; for anonymous users a UUID created only when a grant is logged (kept in AsyncStorage). Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
- Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`.
- The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
- No backend or no such endpoint: report the gap (consents stored only on the device), with the field list: `subject_id`, `created_at` UTC, `consent_version`, `text_sha256`, `channel`, `form_id`, `ip`, `user_agent`, `action` (`grant`/`revoke`).

## Footer and links
Mobile apps have no footer. Link Политика / Оферта / Возврат / Реквизиты from the Documents screen, and show the policy link on the sign-up/login screen and next to every consent checkbox. If an About/Settings screen shows the app version, add the About-screen owner block (template section 3.4, [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites)) from `.legal/answers.json` beneath it; never invent values.

## i18n
- i18next: add keys to the existing `src/locales/ru.json` and `en.json` (or per-namespace folders): `documents.*`, `consent.*`, `legal.translationNotice`. `useTranslation()` in screens.
- react-intl/lingui/i18n-js: same keys in the same catalogs and extraction step.
- RU strings and documents are authoritative. EN strings and EN links are translations; show `legal.translationNotice` on the Documents screen when the UI is EN and link the RU document as authoritative.
- No i18n setup: keep strings in one `strings.ts`; do not add a library.

## Verify and record state
- `npx tsc --noEmit`, `npm run lint`, `npm test` if present. Expo: `npx expo-doctor`. A native build is slow and may rewrite native folders: run `expo prebuild` or `pod install` only with the user's go-ahead.
- Sanity-check by search: no `AppMetrica.activate` or `setAnalyticsCollectionEnabled(…, true)` outside `src/analytics/consent.ts`.
- If a simulator is available, launch fresh (cleared storage) and confirm the banner appears and no analytics call happens before Accept.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
