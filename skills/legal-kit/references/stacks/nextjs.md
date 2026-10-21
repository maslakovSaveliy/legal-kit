# Next.js (App Router and Pages Router)

Mechanics for editing an existing Next.js project. The knowledge pack decides which forms need consent and which texts to show; this file only shows how to wire them in. Reuse the project's Layout, UI kit, form and i18n pieces. Add no UI library.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- `package.json` has `next`. Router: `app/` or `src/app/` (App Router) vs `pages/` (Pages Router); both can coexist.
- UI kit: `components.json` (shadcn/ui), `@mui/material`, `@chakra-ui/react`, `@mantine/core`, `antd`, Tailwind (`tailwind.config.*` or `@import "tailwindcss"` in global CSS), CSS Modules, `styled-components`.
- Forms: `react-hook-form`, `formik`, `@tanstack/react-form`, server actions (`'use server'`, `useActionState`), plain `<form>`. Validation: `zod`, `yup`, `valibot`.
- i18n: `next-intl` (`messages/*.json`, `i18n/request.ts`), `react-i18next`/`next-i18next` (`public/locales/<lng>/*.json`), `react-intl`, `lingui`, or none.
- Analytics today: `grep -rnE "mc.yandex.ru|ym\(|googletagmanager|gtag|connect.facebook.net|vk.com/rtrg|top-fwz1" app src pages components`; packages `react-yandex-metrika`, `@next/third-parties`, `react-ga4`.
- Backend/ORM: `prisma/schema.prisma`, `drizzle.config.ts`, `typeorm`, `mongoose`; Route Handlers in `app/api/**/route.ts`.
- Package manager from the lockfile (`pnpm-lock.yaml`, `yarn.lock`, `bun.lock`, `package-lock.json`).

## Legal pages
- App Router: one page per document, `app/legal/<slug>/page.tsx` (or `app/[locale]/legal/<slug>/page.tsx` when the project is locale-routed; mirror its folder layout). Optional `app/legal/layout.tsx` wrapping the project's existing container/prose component. Keep them Server Components. With an i18n catalog the page title is a catalog key, so export `generateMetadata` that reads it, never a static `metadata` string: with `next-intl` `const t = await getTranslations({ locale, namespace: 'Legal' })` (`locale` from the awaited `params`) and `return { title: t('<slug>.title') }`; without a catalog export `metadata` like sibling pages do.
- Pages Router: `pages/legal/<slug>.tsx` using the project's page wrapper (`getLayout` pattern or `<Layout>`).
- Existing route takes priority: search first (`grep -rniE "privacy|policy|oferta|offer|terms|refund" app pages components`, menus, sitemap) and update that page; never create a duplicate policy page. Only when no route exists use `/legal/{privacy,offer,refund,requisites}` (slugs from the documents step).
- Content: render the Markdown from the documents step the way the project already renders prose (`@next/mdx`, `contentlayer`, `react-markdown`). If none exists, emit the text as JSX in the page file. Do not add a Markdown dependency.
- Add the URLs to `app/sitemap.ts` / `next-sitemap.config.js` if present. Do not add `noindex`.
- Static: no `use client`, no data fetching. Check the `middleware.ts` (named `proxy.ts` since Next 16) matcher and auth guards do not redirect `/legal/*` to login.

## Consent checkbox in forms
- Unchecked by default (`defaultValues: { consentPd: false }`), its own field, separate from "accept the offer/terms". Label text comes from i18n; the policy link opens in a new tab and sits outside the clickable label area.
- Submit stays enabled unless the knowledge pack says consent is required for that form. When required: disable the button (`disabled={!values.consentPd}`) AND enforce on the server; never rely on the client alone.
- Use the project's own `Checkbox`. Prop mapping:

| UI kit | value | change handler |
|---|---|---|
| shadcn/Radix | `checked` | `onCheckedChange={field.onChange}` |
| MUI | `checked` | `onChange={(e) => field.onChange(e.target.checked)}` |
| Chakra v2 | `isChecked` | `onChange={(e) => field.onChange(e.target.checked)}` |
| Chakra v3 | `checked` | `onCheckedChange={(e) => field.onChange(!!e.checked)}` (receives `{ checked }`) |
| Mantine, antd | `checked` | `onChange={(e) => field.onChange(e.currentTarget.checked)}` (antd: `e.target.checked`) |
| none | native `<input type="checkbox">` | `{...register('consentPd')}` |

```tsx
<Controller name="consentPd" control={control} render={({ field, fieldState }) => (
  <Checkbox id="consent-pd" checked={!!field.value} onCheckedChange={field.onChange}
    aria-invalid={!!fieldState.error} /> )} />
```
- Zod: `consentPd: z.boolean().refine(Boolean)` when required, `z.boolean().default(false)` otherwise. Server actions: `formData.get('consentPd') === 'on'`.
- When the consent log exists, call it after a successful submit with this form's `formId`.

## Analytics gated by consent
Keep one consent store. Counters render only from it; on a fresh visit nothing loads.
```ts
// lib/consent.ts
'use client';
import { useSyncExternalStore } from 'react';
export type Consent = { v: string; analytics: boolean; marketing: boolean; at: string };
export const CONSENT_VERSION = '1';   // bump when the consent texts change
const KEY = 'legal_consent', EVT = 'legal-consent', SSR = '__ssr__';
const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
const subscribe = (cb: () => void) => {
  window.addEventListener(EVT, cb); window.addEventListener('storage', cb);
  return () => { window.removeEventListener(EVT, cb); window.removeEventListener('storage', cb); };
};
export function saveConsent(c: Consent) {
  try { localStorage.setItem(KEY, JSON.stringify(c)); } catch {}
  window.dispatchEvent(new Event(EVT));
}
function parse(raw: string | null): Consent | null {
  try { const c = raw ? (JSON.parse(raw) as Consent) : null; return c && c.v === CONSENT_VERSION ? c : null; } catch { return null; } // old version = no valid choice
}
export function useConsent(): Consent | null | undefined { // undefined = still hydrating
  const raw = useSyncExternalStore(subscribe, read, () => SSR);
  return raw === SSR ? undefined : parse(raw);
}
export const openConsentSettings = () => window.dispatchEvent(new Event('legal-consent-open')); // footer link: reopens the banner, keeps the stored choice
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
  if (granted) logConsent('grant');       // logConsent: see Consent log; delete both calls when the project has no backend
  if (revoked) { logConsent('revoke'); purgeCounterCookies(); location.reload(); }
}
```
```tsx
// components/consent-gated-analytics.tsx
'use client';
import Script from 'next/script';
import { useConsent } from '@/lib/consent';
export function ConsentGatedAnalytics() {
  const consent = useConsent();
  if (!consent?.analytics) return null;
  return (
    <Script id="ym" strategy="afterInteractive">{`/* paste the project's existing Metrica init here, unchanged */`}</Script>
  );
}
```
- Mount it once in `app/layout.tsx` (or `pages/_app.tsx`) next to `{children}`. `next/script` inline scripts need an `id`.
- One rule everywhere: analytics counters (Metrica, GA, GTM) render only when `consent.analytics`; ad pixels (VK, Meta, TikTok) only when `consent.marketing`, in a sibling component of the same shape.
- Move every existing counter behind its condition: Metrica, GA (`<GoogleAnalytics gaId=... />` and `<GoogleTagManager />` from `@next/third-parties/google` load immediately, so render them conditionally; a GTM container loaded early can fire any tag), VK/Meta/TikTok pixels, `react-yandex-metrika`'s `<YMInitializer>`.
- Delete `<noscript><img src="https://mc.yandex.ru/watch/...">` pixels and any `<link rel="preconnect|dns-prefetch">` to counter hosts; they fire without consent.
- Page views on client navigation: keep the project's existing `usePathname` effect, but return early when `!consent?.analytics`.
- Revoke: the footer link "Cookie settings" only calls `openConsentSettings()` (it must not clear the stored choice). Reject or Save then go through `decide()`, which compares with the stored choice, logs `revoke` when a granted category turns off, deletes the counter cookies and reloads (an already-loaded script cannot be unloaded).
- Server components and middleware must not set analytics cookies or fire server-side events before consent.

## Consent banner
- Client component `components/consent-banner.tsx` built from the project's existing `Button`, `Card`/`Alert` and design tokens (CSS variables or Tailwind theme classes); no new CSS framework, no new fonts.
- Show it when `useConsent() === null` (not when `undefined`, to avoid a flash). Accept all and Reject use the same Button component and size. Texts via `useTranslations('Consent')`; link to the policy page.
- Accept all sets `analytics` and `marketing`; Reject sets neither; a Settings view offers two separate toggles (the project's `Switch`/`Checkbox`, unchecked by default) and Save.
- Accept all calls `decide(true, true)`, Reject `decide(false, false)`, Save `decide(analyticsToggle, marketingToggle)`. The banner shows when `useConsent() === null` or after `legal-consent-open` (local `reopened` state, reset after `decide`), with the toggles pre-filled from the stored choice. After a `CONSENT_VERSION` bump the stored value no longer matches, `useConsent()` returns `null`, so the banner reappears and counters stop until the new choice.
- Mount next to `ConsentGatedAnalytics`. Add a footer link "Cookie settings" calling `openConsentSettings()` (the revoke path; it never clears the stored choice, so `decide()` can still see what was granted).

## Consent log (existing backend only)
Only if the repo already has a database and ORM. NEVER introduce a new database, ORM or service. No backend: do not build one; report the gap (consents are visible only in the browser).
Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`. Anonymous `subjectId`: a persistent UUID created when a grant is logged. Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
```prisma
model ConsentLog {            // append-only: no update/delete code path
  id String @id @default(cuid())
  subjectId String @map("subject_id")      // user id, else anonymous UUID (persistent only after Accept)
  createdAt DateTime @default(now()) @map("created_at")   // UTC
  consentVersion String @map("consent_version")
  textSha256 String @map("text_sha256")
  channel String                           // web | ios | android
  formId String @map("form_id")
  ip String?
  userAgent String? @map("user_agent")
  action String                            // grant | revoke
  @@index([subjectId, createdAt])
  @@map("consent_log")
}
```
```ts
// app/api/consent/route.ts   (prisma: the project's existing client module; CONSENT_TEXTS: { [version]: text })
import { createHash } from 'node:crypto';
export async function POST(req: Request) {
  let b: any;
  try { b = await req.json(); } catch { return new Response(null, { status: 400 }); }   // invalid JSON is a 400, not a 500
  // validate with the project's validator (zod); for signed-in users take subjectId from the session
  const text = CONSENT_TEXTS[b.consentVersion];   // known text per version; never trust a client hash
  if (!text) return new Response(null, { status: 400 });
  await prisma.consentLog.create({ data: { subjectId: b.subjectId, consentVersion: b.consentVersion,
    textSha256: createHash('sha256').update(text).digest('hex'),
    channel: ['web', 'ios', 'android'].includes(b.channel) ? b.channel : 'web', formId: b.formId,
    ip: req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ?? null,   // spoofable unless a trusted proxy/platform sets it; otherwise store null
    userAgent: req.headers.get('user-agent'), action: b.action } });
  return new Response(null, { status: 204 });
}
```
- Other ORMs (Drizzle, TypeORM, Mongoose): same columns, same insert-only rule, the project's migration tool.
- Migrations: never apply one. `prisma migrate dev --create-only --name add_consent_log` (or another generator that connects to the database) runs only when the configured database host is `localhost`, `127.0.0.1`, `::1` or a local socket; otherwise write the Prisma SQL migration by hand (format in [nestjs.md](nestjs.md)) or leave the command in «Сделать вам». Rules: [ui-integration.md](../workflow/ui-integration.md#consent-log).
- Optional hardening: DB trigger or revoked UPDATE/DELETE grants, only if migrations already contain raw SQL.
- Client side, in `lib/consent.ts`; call it from `decide()` (`formId: 'cookie-banner'`) and from successful form submits, only for a grant or a revoke (never for a first-time refusal):
```ts
function subjectId() {   // anonymous id: created when a grant is logged; signed-in users send their user id instead
  try { let v = localStorage.getItem('legal_subject'); if (!v) { v = crypto.randomUUID(); localStorage.setItem('legal_subject', v); } return v; } catch { return 'anon'; }
}
export function logConsent(action: 'grant' | 'revoke', formId = 'cookie-banner') {
  fetch('/api/consent', { method: 'POST', keepalive: true, headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ subjectId: subjectId(), consentVersion: CONSENT_VERSION, formId, channel: 'web', action }) }).catch(() => {});
}
```

## Footer and links
Find the footer (`components/Footer*`, `layout/footer`, `<footer>` in `app/layout.tsx`). Add Политика / Оферта / Возврат / Реквизиты links to its existing link list (data array or JSX), using `next/link` and i18n keys. Also link the policy next to every consent checkbox and in the banner. If the footer prints a copyright line, extend it only to the short footer form of the owner's status (name, OGRN or OGRNIP where section 3.2 prints it, address, e-mail; INN only for a self-employed owner) from `.legal/answers.json`; never invent values. The owner details the footer shows (which requisites, by the owner's status) follow [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites).

## i18n
- next-intl: add a `Legal` namespace to `messages/ru.json` and `messages/en.json`; `useTranslations('Legal')` in client code, `await getTranslations('Legal')` in Server Components; links inside strings via `t.rich`.
- i18next/react-intl/lingui: the same keys in the existing catalogs, same extraction step.
- RU strings and documents are authoritative. EN versions are translations: add a catalog key such as `Legal.translationNotice` and render it at the top of every EN legal page.
- Do not hard-code Russian or English UI text in components when the project has catalogs.

## Verify and record state
- `npx tsc --noEmit`, `npm run lint` (the project's script; `next lint` was removed in Next 16, so a bare `next lint` call means an older Next), `npm run build`, `npm test` if present. Use the lockfile's package manager.
- Rerun the grep from Detect: remaining counter hosts must appear only inside the gated component. In a browser with empty storage, no request to counter hosts may occur before Accept.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
