# Generic web fallback (Vue/Nuxt, Svelte/SvelteKit, Angular, PHP, anything else)

Use when no dedicated stack file fits: Vue 3 + Vite, Nuxt, SvelteKit, Angular, Laravel, Symfony, plain PHP, Rails, Go templates, Spring and similar. The goal is the same everywhere: legal pages in the existing layout, an unchecked consent checkbox, counters loaded only after consent, a banner, a footer link set, and a consent log only on an existing database. The knowledge pack decides which forms need consent and which texts to show; this file shows mechanics. Reuse the project's layout, UI kit, forms and i18n. Add no library and no new database.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
| Stack | Recognize by | Layout / pages live in | i18n |
|---|---|---|---|
| Vue 3 (Vite) | `vue`, `vue-router`, `src/App.vue`, `src/router/index.ts` | `src/views/*.vue`, `App.vue` | `vue-i18n` (`src/locales/*.json`) |
| Nuxt | `nuxt.config.ts`, `app.vue`, `pages/`, `layouts/` | `pages/`, `layouts/default.vue` | `@nuxtjs/i18n` (`i18n/locales`, `locales/`) |
| SvelteKit | `svelte.config.js`, `src/routes/+layout.svelte` | `src/routes/**/+page.svelte` | `svelte-i18n`, `paraglide`, `typesafe-i18n` |
| Angular | `angular.json`, `app.routes.ts` | `src/app/**`, `app.component.html` | `@ngx-translate/core`, `@angular/localize` (`messages.xlf`) |
| Laravel | `artisan`, `composer.json` with `laravel/framework`, `routes/web.php` | `resources/views/layouts/*.blade.php` | `lang/<locale>/*.php`, `lang/<locale>.json` |
| Symfony | `symfony.lock`, `config/routes.yaml`, `templates/base.html.twig` | `templates/` | `translations/*.xlf\|yaml` |
| Plain PHP / WordPress-less CMS | `index.php`, `include 'header.php'` | `header.php`, `footer.php` | arrays, `gettext` |
| Rails / Go / Spring / .NET | `Gemfile`+`config/routes.rb`; `go.mod`+`html/template`; `pom.xml`+Thymeleaf; `*.csproj`+Razor | view layouts | framework catalogs |

Also detect: UI kit (Vuetify, PrimeVue, Element Plus, Quasar, Angular Material, Bootstrap, Tailwind), forms (VeeValidate, Vuelidate, Angular reactive forms, Symfony forms, Laravel validation), counters (`grep -rnE "mc.yandex.ru|ym\(|googletagmanager|gtag|connect.facebook.net|vk.com/rtrg"` over templates, layouts, `public/`), ORM (Eloquent, Doctrine, ActiveRecord, GORM, JPA).

## Legal pages
0. Existing route takes priority: search first (`grep -rniE "privacy|policy|oferta|offer|terms"` over routes, templates, menus, sitemap) and update that page; never create a duplicate policy page. Only when none exists use `/legal/{privacy,offer,refund,requisites}` (slugs from the documents step).
1. Find the layout used by an existing content page (about, contacts). Create each document page with that same layout.
2. Register the route the project's way: Vue router entry or `pages/legal/[slug].vue` (Nuxt); `src/routes/legal/<slug>/+page.svelte`; Angular route in `app.routes.ts` with a standalone component; Laravel `Route::view('/legal/privacy', 'legal.privacy')`; Symfony a controller with `#[Route('/legal/privacy')]`; plain PHP a file `legal/privacy.php` including `header.php`/`footer.php`.
3. Content: the document text from the documents step as markup (convert Markdown by hand or one-off script; no new Markdown package). Allowlist the slugs when one route serves several documents.
4. Add to sitemap if present; make sure auth guards/middleware do not cover `/legal/*`; for static hosting of an SPA make sure the host serves the app for these paths.

## Consent checkbox in forms
Unchecked by default, its own field, separate from the offer/terms checkbox; policy link outside the clickable label. Submit stays enabled unless the knowledge pack says consent is required for that form; then disable the button AND validate on the server.
- Vue: `const form = reactive({ consentPd: false })`, `<input type="checkbox" id="consent-pd" v-model="form.consentPd">` (UI kit: `v-checkbox`, `el-checkbox`, `Checkbox` from PrimeVue); `:disabled="required && !form.consentPd"`.
- Svelte: `let consentPd = $state(false)` (Svelte 5; `let consentPd = false` in 4), `<input type="checkbox" bind:checked={consentPd}>`.
- Angular: `consentPd: [false, Validators.requiredTrue]` (required) or `[false]`; `<input type="checkbox" formControlName="consentPd">` or `<mat-checkbox>`.
- Laravel: rule `'consent_pd' => ['accepted']` (required) or `['sometimes', 'boolean']`; Blade `<input type="checkbox" name="consent_pd" value="1">` (no `checked`; `old()` may restore the user's own choice after a failed validation). Symfony: `CheckboxType` + `IsTrue` constraint when required. Plain PHP: `if (empty($_POST['consent_pd'])) { http_response_code(422); exit; }`.
- Always send the value and a `form_id` to the server; never rely on the front end alone.

## Analytics gated by consent
Default, works in every stack: use the plain-JS loader `consent.js` from `static-html.md` (copy it into the framework's public/static folder, include it with `defer` from the root layout, give counter IDs through `data-` attributes from config). Remove the original inline counters and `<noscript><img src="https://mc.yandex.ru/watch/...">` pixels first.
- Framework-native alternative (use only if the project already keeps global state; `/js/metrika-init.js` below is a file holding the original init code removed from the layout):
  - Nuxt: `const consent = useCookie<{ v: string; analytics: boolean; marketing: boolean } | null>('legal_consent', { maxAge: 60 * 60 * 24 * 180, sameSite: 'lax', default: () => null })` and `useHead(() => consent.value?.v === CONSENT_VERSION && consent.value.analytics ? { script: [{ src: '/js/metrika-init.js', defer: true }] } : {})` in `app.vue` (verify `useHead` script options against the installed Nuxt). The version check makes a bumped `CONSENT_VERSION` reopen the banner and stop counters.
  - SvelteKit: a `writable` store persisted to `localStorage` inside `onMount` (guard `browser`; treat a stored `v` different from `CONSENT_VERSION` as no choice). `<svelte:head>` must stay at the top level of the component and never inside a block, so the condition goes inside it: `<svelte:head>{#if $consent?.analytics}<script src="/js/metrika-init.js" defer></script>{/if}</svelte:head>` in the root layout. An already inserted script is not unloaded: reload on revoke.
  - Vue/Angular: a service/composable holding the choice (version-checked as above); inject the script element (`document.createElement('script')`) from an effect/`ngOnInit` only when analytics is granted.
  - Laravel/Symfony/PHP: do not branch on a cookie in the template if pages are cached; keep `consent.js`.
- One rule everywhere: analytics counters (Metrica, GA, GTM) start only when `analytics` is granted; ad pixels (VK, Meta, TikTok) only when `marketing` is granted.
- Revoke: footer link `data-consent="reopen"` (as in `static-html.md`) or the framework's store; after revoke delete counter cookies (`_ym_*`, `_ga*`, `_gid`, `_fbp`) and reload, since a loaded script cannot be unloaded.
- Server-side events (offline conversions, pixel APIs) fire only after a recorded `grant`.

## Consent banner
Build it from the project's existing components (Vuetify `v-snackbar`/`v-banner`, Bootstrap toast, Angular Material snackbar/dialog, a Svelte component, a Blade/Twig partial) and its design tokens; no new library. With `consent.js`, render the markup from `static-html.md` (`#consent-banner`, `data-consent` buttons) inside a component or partial. Accept all and Reject use the same component and size; Accept all sets `analytics` and `marketing`, Reject sets neither, and a Settings view has two separate toggles, unchecked by default; texts come from the project's i18n catalogs; link to the policy page. A bumped consent version makes the stored choice invalid, so the banner returns.

## Consent log (existing backend only)
Only with an existing database and ORM. NEVER introduce a new database, ORM or migration tool. Append-only table `consent_log`: `subject_id`, `created_at` (UTC), `consent_version`, `text_sha256` (computed on the server from the known text of that version), `channel`, `form_id`, `ip`, `user_agent`, `action`. Endpoint `POST` that validates, inserts, returns 204 (400 on invalid JSON); no update/delete path; CSRF stays on (pass the token through `data-csrf-*`).
Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`. Request keys are camelCase, columns snake_case; the handler maps them. Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data. `consent.js` sends exactly this payload.
The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
```php
// Laravel migration (Eloquent model: $timestamps = false; booted(): static::updating(fn () => false); static::deleting(fn () => false);)
Schema::create('consent_log', function (Blueprint $t) {
    $t->id(); $t->string('subject_id', 128)->index(); $t->timestampTz('created_at')->useCurrent();  // useCurrent() is the DB clock, not app.timezone: use timestampTz (Postgres) or a UTC DB session time zone (MySQL)
    $t->string('consent_version', 32); $t->char('text_sha256', 64); $t->string('channel', 8);
    $t->string('form_id', 64); $t->string('ip', 45)->nullable(); $t->text('user_agent')->nullable(); $t->string('action', 6);
});
```
- Laravel handler: `$request->validate(['subjectId' => 'required|string|max:128', 'consentVersion' => 'required|string|max:32', 'formId' => 'required|string|max:64', 'channel' => 'in:web,ios,android', 'action' => 'in:grant,revoke'])`, then `$request->ip()` (honours the TrustProxies setup), `$request->userAgent()`, `hash('sha256', $text)` with `$text` from the known text of that version; Symfony/Doctrine, Rails/ActiveRecord, GORM, JPA: same columns with the project's migration tool. Never apply a migration; a generator that connects to the database runs only for a `localhost`, `127.0.0.1`, `::1` or local-socket host, otherwise the command goes to «Сделать вам» ([ui-integration.md](../workflow/ui-integration.md#consent-log)).
- Nuxt/SvelteKit server routes (`server/api/consent.post.ts`, `+server.ts`) can write through an ORM the project already has. Without one, or without any backend: report the gap.

## Footer and links
Find the shared footer (layout, partial, `footer.php`, `app.component.html`). Add Политика / Оферта / Возврат / Реквизиты to its existing link list with the framework's link component (`router-link`, `NuxtLink`, `<a>`, `routerLink`, `route()`), with i18n keys; also next to each consent checkbox and in the banner, plus a "Cookie settings" link that reopens the banner. If a copyright line exists, extend it only to the short footer form of the owner's status (name, OGRN or OGRNIP where section 3.2 prints it, address, e-mail; INN only for a self-employed owner) from `.legal/answers.json`; never invent values. The owner details the footer shows (which requisites, by the owner's status) follow [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites).

## i18n
- Put strings in the existing catalogs: `vue-i18n` `$t('legal.consent')`, Nuxt `$t` + locale files, `svelte-i18n` `$_()`, Angular `translate` pipe / `$localize`, Laravel `__('legal.consent')` (`lang/ru/legal.php`, `lang/en/legal.php`), Symfony `trans` + `translations/legal.ru.yaml`.
- RU strings and documents are authoritative. EN versions are translations marked with a notice key (`legal.translation_notice`) rendered at the top of every EN legal page.
- No i18n in the project: keep one language and a constants file; add no library.

## Verify and record state
- JS stacks: `npx tsc --noEmit` / `npx vue-tsc --noEmit` / `npx svelte-check` / `npx ng build`, `npm run lint`, `npm run build`, `npm test` (use the lockfile's package manager). Nuxt: `npx nuxi typecheck`.
- PHP: `php -l <file>`, `php artisan route:list | grep legal`, `php artisan test`, `composer lint` if defined. Others: the project's compile/test command.
- Counter hosts must remain only in the loader; in a browser with empty storage no counter request before Accept.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
