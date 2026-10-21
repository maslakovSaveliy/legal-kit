# React SPA (Vite, CRA, React Router, TanStack Router)

Mechanics for editing an existing client-side React app. For Next.js use `nextjs.md`. The knowledge pack decides which forms need consent and which texts to show; this file only shows how to wire them in. Reuse the project's Layout, UI kit, form and i18n pieces. Add no UI library.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- `package.json` has `react` and no `next`. Bundler: `vite.config.*` (+ `index.html` at the root), `react-scripts` (CRA), `webpack.config.*`, `rsbuild`/`rspack`.
- Router: `react-router-dom` / `react-router` (`createBrowserRouter`, `<Routes>`; framework mode has `app/routes.ts` and `@react-router/dev`), `@tanstack/react-router` (`routeTree.gen.ts`), `wouter`. Entry: `src/main.tsx` or `src/index.tsx`, routes often in `src/App.tsx` or `src/router.tsx`.
- UI kit: `@mui/material`, `antd`, `@chakra-ui/react`, `@mantine/core`, shadcn (`components.json`), Tailwind, CSS Modules, `styled-components`.
- Forms: `react-hook-form`, `formik`, `react-final-form`, antd `<Form>`, plain controlled inputs. Validation: `zod`, `yup`.
- i18n: `react-i18next` (`src/locales/*.json`, `public/locales`), `react-intl`/`@formatjs`, `lingui`, none.
- Analytics today: `grep -rnE "mc.yandex.ru|ym\(|googletagmanager|gtag|connect.facebook.net|vk.com/rtrg" index.html public src`; counters pasted into `index.html` are the usual place.
- Backend: usually a separate API (`axios`/`fetch` base URL in `src/api`, `.env` `VITE_API_URL`). A `server/` or `api/` folder with an ORM in the same repo counts as a backend.

## Legal pages
- Add one route per document in the existing router config, wrapped in the same layout route as other content pages (`<Route element={<Layout />}>` or the layout in `createBrowserRouter`). Existing route takes priority: search first (`grep -rniE "privacy|policy|oferta|offer|terms|refund" src public`, router config, menus) and update that page; never create a duplicate policy page. Only when none exists use `/legal/{privacy,offer,refund,requisites}` (slugs from the documents step).
- Page component under the project's pages folder (`src/pages/legal/PrivacyPage.tsx`), reusing the existing page/container/typography components. Follow the project's lazy-loading style (`React.lazy` if siblings use it).
- Content: render the Markdown the way the project already does (`react-markdown`, MDX plugin). Otherwise write the text as JSX in the page component; do not add a Markdown dependency.
- SPA hosting must return `index.html` for `/legal/*` so direct links and crawlers work: check `vercel.json` rewrites, Netlify `_redirects`/`netlify.toml`, nginx `try_files`, Firebase `rewrites`. If the host has no fallback, report it. If the project prerenders (vite-ssg, react-snap), add the routes to its list.
- Add the URLs to `public/sitemap.xml` if the project keeps one. Set the page title the way siblings do (`react-helmet-async`, `document.title` effect).

## Consent checkbox in forms
- Unchecked by default (`defaultValues: { consentPd: false }`; `useState(false)`), its own field, separate from "accept the offer/terms". Label from i18n; the policy link opens in a new tab (`target="_blank" rel="noopener"`) and sits outside the clickable label area.
- Submit stays enabled unless the knowledge pack says consent is required for that form. When required: `disabled={!values.consentPd}` plus validation on the API side; the client alone is not enough.
- Use the project's own `Checkbox`. With react-hook-form:
```tsx
<Controller name="consentPd" control={control} render={({ field }) => (
  <Checkbox checked={!!field.value} onChange={(e) => field.onChange(e.target.checked)}>{t('consent.pd')}</Checkbox>
)} />
```
- Prop shapes: MUI `checked`/`onChange(e.target.checked)`; antd `checked`/`onChange(e.target.checked)`; Chakra v2 `isChecked`/`onChange(e.target.checked)`, Chakra v3 `checked`/`onCheckedChange((e) => e.checked)`; Mantine `checked`/`onChange(e.currentTarget.checked)`; shadcn/Radix `checked`/`onCheckedChange(value)`; no kit: native `<input type="checkbox" {...register('consentPd')} />`.
- Validation: `z.boolean().refine(Boolean, { message: t('consent.required') })` when required; plain `z.boolean()` otherwise. Send the boolean (and the `formId`) in the request body so the backend can verify it.

## Analytics gated by consent
Move every counter out of `index.html` into one loader that runs only after consent.
```ts
// src/lib/consent.ts
import { useSyncExternalStore } from 'react';
export type Consent = { v: string; analytics: boolean; marketing: boolean; at: string };
export const CONSENT_VERSION = '1';   // bump when the consent texts change
const KEY = 'legal_consent', EVT = 'legal-consent';
const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const subscribe = (cb: () => void) => {
  addEventListener(EVT, cb); addEventListener('storage', cb);
  return () => { removeEventListener(EVT, cb); removeEventListener('storage', cb); };
};
export function saveConsent(c: Consent) {
  try { localStorage.setItem(KEY, JSON.stringify(c)); } catch {}
  dispatchEvent(new Event(EVT));
}
function parse(raw: string | null): Consent | null {
  try { const c = raw ? (JSON.parse(raw) as Consent) : null; return c && c.v === CONSENT_VERSION ? c : null; } catch { return null; } // old version = no valid choice
}
export function useConsent(): Consent | null {
  return parse(useSyncExternalStore(subscribe, read, () => null));
}
export const openConsentSettings = () => dispatchEvent(new Event('legal-consent-open')); // footer link: reopens the banner, keeps the stored choice
function purgeCounterCookies() {
  const host = location.hostname.split('.').slice(-2).join('.');   // registrable-domain guess: verify on the real host
  document.cookie.split(';').map((c) => c.split('=')[0].trim()).filter((n) => /^(_ym_|_ga|_gid|_fbp)/.test(n))
    .forEach((n) => ['', `;domain=${host}`, `;domain=.${host}`].forEach((d) => { document.cookie = `${n}=;max-age=0;path=/${d}`; }));
}
export function decide(analytics: boolean, marketing: boolean) {   // Accept all, Reject and Save all call this
  const was = parse(read());
  const granted = (analytics && !was?.analytics) || (marketing && !was?.marketing);
  const revoked = !!was && ((was.analytics && !analytics) || (was.marketing && !marketing));
  saveConsent({ v: CONSENT_VERSION, analytics, marketing, at: new Date().toISOString() });
  if (granted) logConsent('grant');       // logConsent: see Consent log; delete both calls when there is no backend
  if (revoked) { logConsent('revoke'); purgeCounterCookies(); location.reload(); }
}
```
If the project already has a store (Redux, Zustand `persist`, Jotai), keep consent there instead of adding this file.
```ts
// src/lib/analytics.ts
export function loadScript(src: string) {
  if (document.querySelector(`script[src="${src}"]`)) return;
  const s = document.createElement('script'); s.async = true; s.src = src; document.head.appendChild(s);
}
export function initMetrica(id: number) {  // copy URL and options from the project's existing snippet
  const w = window as any;
  w.ym = w.ym || function () { (w.ym.a = w.ym.a || []).push(arguments); };  // same queue stub as the official snippet
  w.ym.l = Date.now();
  loadScript('https://mc.yandex.ru/metrika/tag.js');
  w.ym(id, 'init', { clickmap: true, trackLinks: true, accurateTrackBounce: true });
}
```
- One rule everywhere: analytics counters (Metrica, GA, GTM) start only when `consent.analytics`; ad pixels (VK, Meta, TikTok) only when `consent.marketing`, through the same loader pattern.
- Run the loader from an effect: `useEffect(() => { if (consent?.analytics) initMetrica(Number(import.meta.env.VITE_YM_ID)); }, [consent?.analytics])`. Mount that component once under the router/provider root. CRA: `process.env.REACT_APP_*`.
- Remove the original snippets from `index.html`, including `<noscript><img src="https://mc.yandex.ru/watch/...">` pixels and preconnect hints to counter hosts. GA, GTM (a container loaded early can fire any tag), VK, Meta and other pixels follow the same loader pattern (inject script, then init call).
- SPA page views: keep the existing route-change effect (`useLocation`) but return early when `!consent?.analytics`.
- Revoke: the footer link "Cookie settings" only calls `openConsentSettings()` (it must not clear the stored choice). Reject or Save then go through `decide()`, which compares with the stored choice, logs `revoke` when a granted category turns off, deletes the counter cookies and reloads (a loaded script cannot be unloaded).

## Consent banner
- Component built from the project's `Button`, `Card`/`Alert` and design tokens (theme object, CSS variables, Tailwind theme); no new CSS framework or fonts. Mount it next to the analytics loader, inside the i18n provider.
- Render when `useConsent() === null`. Accept all and Reject use the same component and size. Texts via `t('consent.banner.*')`; link to the policy route with the router's `<Link>`.
- Accept all sets `analytics` and `marketing`; Reject sets neither; a Settings view offers two separate toggles (the project's `Switch`/`Checkbox`, unchecked by default) and Save.
- Accept all calls `decide(true, true)`, Reject `decide(false, false)`, Save `decide(analyticsToggle, marketingToggle)`. The banner shows when `useConsent() === null` or after `legal-consent-open` (local `reopened` state, reset after `decide`), with the toggles pre-filled from the stored choice. After a `CONSENT_VERSION` bump the stored value no longer matches, `useConsent()` returns `null`, so the banner reappears and counters stop until the new choice. The footer link "Cookie settings" calls `openConsentSettings()` and never clears the stored choice.

## Consent log (existing backend only)
- An SPA alone has no storage: NEVER introduce a new database, BaaS or serverless function for this. If the repo contains the backend (`server/`, `api/`, Express/Nest/Fastify with Prisma, TypeORM, Drizzle, Sequelize, Mongoose), follow `nestjs.md` (TypeORM entity, controller) or `nextjs.md` (Prisma model, handler) on that backend.
- Columns, append-only: `subject_id`, `created_at` (UTC), `consent_version`, `text_sha256` (computed server-side from the known text of that version), `channel`, `form_id`, `ip`, `user_agent`, `action`.
- Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`.
- Client side, in `src/lib/consent.ts`: `export const logConsent = (action: 'grant' | 'revoke', formId = 'cookie-banner') => api.post('/consents', { subjectId: subjectId(), consentVersion: CONSENT_VERSION, formId, channel: 'web', action }).catch(() => {});` (`api` = the project's API client; `subjectId()` = the user id when logged in, else a UUID persisted in `localStorage` when a grant is logged). `decide()` calls it; also call it after each consent-bearing submit, only for a grant or a revoke (never after a first-time refusal). Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
- The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
- Backend in another repo or absent: do not call a non-existent endpoint. Report the gap and give the owner the request contract above.

## Footer and links
Find the footer component (`src/components/Footer*`, `layouts/`). Add Политика / Оферта / Возврат / Реквизиты to its existing link data, with the router `<Link>` and i18n keys. Link the policy next to every consent checkbox and in the banner. If a copyright line exists, extend it only to the short footer form of the owner's status (name, OGRN or OGRNIP where section 3.2 prints it, address, e-mail; INN only for a self-employed owner) from `.legal/answers.json`; never invent values. The owner details the footer shows (which requisites, by the owner's status) follow [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites).

## i18n
- react-i18next: add keys under a `legal` namespace in `src/locales/ru/*.json` and `en/*.json` (same file layout as existing namespaces), use `useTranslation('legal')`. `Trans` for sentences containing links.
- react-intl: add ids to the existing message files and extract with the project's script. lingui: `t` macro + `lingui extract`.
- RU strings and documents are authoritative. EN versions are translations: add `legal.translationNotice` and render it on every EN legal page.
- No catalogs in the project: keep the strings in one constants file; do not add an i18n library.

## Verify and record state
- `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npm test` if present (use the lockfile's package manager).
- `grep` from Detect again: counter hosts must remain only in the loader. In a browser with empty storage, no request to counter hosts before Accept.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
