# Static HTML sites (plain HTML, Astro, Eleventy, Hugo, Jekyll)

Mechanics for editing a site made of HTML files, with or without a static site generator. This file also holds the plain-JS consent loader and banner reused by `python.md`, `generic-web.md` and `no-code.md`. The knowledge pack decides which forms need consent and which texts to show; this file shows the mechanics. Reuse the site's own CSS and markup. Add no framework or library.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- Plain: `index.html` at the root or in `public/`, `docs/`; few or no `package.json` scripts. Generators: Astro (`astro.config.*`, `src/pages`, `src/layouts`), Eleventy (`.eleventy.js`, `_includes`), Hugo (`hugo.toml`, `layouts/`, `content/`), Jekyll (`_config.yml`, `_layouts`, `_includes`).
- Hosting hints: `netlify.toml`/`_redirects`, `vercel.json`, `CNAME` + Pages workflow, `.htaccess`, an nginx config. They decide whether `legal/privacy` works without `.html`.
- CSS/JS: Bootstrap or Tailwind via CDN/CLI, `css/style.css`, jQuery. Reuse existing classes and CSS variables.
- Forms: `<form action="https://formspree.io/...">`, Netlify Forms (`data-netlify`), `mailto:`, a PHP/Node handler (`send.php`), a Telegram-bot webhook, an embedded Google Form.
- Analytics today: `grep -rnE "mc.yandex.ru|ym\(|googletagmanager|gtag|connect.facebook.net|vk.com/rtrg" --include=*.html --include=*.astro --include=*.njk --include=*.md .`
- Multilingual: `/en/` folders, `hreflang` links, `data-i18n` attributes with JSON. Backend: usually none (see Consent log).

## Legal pages
- Existing route takes priority: search first (`grep -rliE "privacy|policy|oferta|offer|terms" --include=*.html --include=*.md --include=*.astro .`, footer links, sitemap) and update that page; never create a duplicate policy page. Only when none exists use `/legal/{privacy,offer,refund,requisites}` (slugs from the documents step).
- Plain HTML: new files `legal/<slug>.html`. If existing pages use clean URLs (`about/index.html`), use `legal/<slug>/index.html`. Copy the full page chrome from an existing content page: `<head>` (meta, CSS links, favicon, canonical pattern), header, footer, scripts. Mind relative asset paths in a subfolder (`../css/style.css`) unless siblings use root-absolute paths.
- Put the document text from the documents step (convert Markdown to HTML by hand or with a one-off script) inside the page's main content container.
- Generators: Astro `src/pages/legal/<slug>.astro` using the existing layout; Eleventy/Jekyll `legal/<slug>.md` with `layout:` front matter; Hugo `content/legal/<slug>.md` with the site's `type`. Keep their front matter conventions (title, description, permalink).
- Add the pages to `sitemap.xml` (or the generator's sitemap config) when one exists. Do not add `noindex`.
- Hosting: confirm the URL the footer will use resolves (`legal/privacy` vs `legal/privacy.html`).

## Consent checkbox in forms
- Unchecked by default (no `checked` attribute), a separate field with its own `name`/`id`, separate from the offer/terms checkbox. The policy link opens in a new tab and sits outside the `<label>` text that toggles the box.
```html
<label class="consent">
  <input type="checkbox" name="consent_pd" id="consent_pd" required>
  <span>[consent text from the documents step]</span>
</label>
<a href="/legal/privacy" target="_blank" rel="noopener">[policy link text]</a>
```
- `required` makes the browser block submit with its native message. Add it only when the knowledge pack says consent is required for this form; otherwise omit it and the submit button stays enabled. A JS-disabled button is not needed.
- Match the site's form markup (wrapper classes, spacing) so the box looks native to the design.
- The consent must reach the handler: Formspree/Netlify include the field automatically; a `mailto:` form cannot carry the flag reliably, so report the limit; for PHP/Node handlers reject a missing `consent_pd` on the server when required, and add the consent flag, `consent_version` and a UTC timestamp to the notification the owner receives.
- Add hidden fields `form_id` and `consent_version` so each submission records which form and text version were used.

## Analytics gated by consent
Delete every inline counter snippet and `<noscript><img src="https://mc.yandex.ru/watch/...">` pixel from all pages and layouts (also `preconnect` hints to counter hosts). Replace them with one script, `consent.js`, included at the end of `<body>` on every page (layout/partial for generators):
```html
<script src="/js/consent.js" defer data-version="1" data-ym="12345678" data-ga="" data-gtm=""></script>
```
Take the IDs and the Metrica init options from the removed snippets. `consent.js`:
```js
(function () {
  var KEY = 'legal_consent', d = (document.currentScript || {}).dataset || {}, VERSION = d.version || '1', started = {};
  function banner() { return document.getElementById('consent-banner'); }
  function ready(fn) { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn); else fn(); }
  function read() { try { var c = JSON.parse(localStorage.getItem(KEY)); return c && c.v === VERSION ? c : null; } catch (e) { return null; } }
  function write(c) { try { localStorage.setItem(KEY, JSON.stringify(c)); } catch (e) {} }
  function once(name, fn) { if (!started[name]) { started[name] = 1; fn(); } }   // re-Accept must not init twice
  function load(src) {
    if (document.querySelector('script[src="' + src + '"]')) return;
    var s = document.createElement('script'); s.async = true; s.src = src; document.head.appendChild(s);
  }
  function startMetrica(id) { once('ym', function () {   // same queue stub as the official snippet; copy URL/options from the removed one
    window.ym = window.ym || function () { (window.ym.a = window.ym.a || []).push(arguments); };
    window.ym.l = Date.now(); load('https://mc.yandex.ru/metrika/tag.js');
    window.ym(Number(id), 'init', { clickmap: true, trackLinks: true, accurateTrackBounce: true });
  }); }
  function startGA(id) { once('ga', function () {
    load('https://www.googletagmanager.com/gtag/js?id=' + id);
    window.dataLayer = window.dataLayer || []; window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date()); window.gtag('config', id);
  }); }
  function startGTM(id) { once('gtm', function () {
    window.dataLayer = window.dataLayer || []; window.dataLayer.push({ 'gtm.start': Date.now(), event: 'gtm.js' });
    load('https://www.googletagmanager.com/gtm.js?id=' + id);
  }); }
  function start(c) {
    if (!c) return;
    if (c.analytics) { if (d.ym) startMetrica(d.ym); if (d.ga) startGA(d.ga); if (d.gtm) startGTM(d.gtm); }
    if (c.marketing) { /* ad pixels (VK, Meta, TikTok): start them here with the same once() pattern */ }
  }
  function purge() {               // counter cookies; guesses the registrable domain: verify on the real host
    var host = location.hostname.split('.').slice(-2).join('.');
    document.cookie.split(';').forEach(function (p) {
      var n = p.split('=')[0].trim();
      if (/^(_ym_|_ga|_gid|_fbp)/.test(n)) ['', ';domain=' + host, ';domain=.' + host].forEach(function (dom) {
        document.cookie = n + '=;max-age=0;path=/' + dom; });
    });
  }
  function uuid() {                // randomUUID is missing on plain-http pages; getRandomValues is not
    if (crypto.randomUUID) return crypto.randomUUID();
    return Array.prototype.map.call(crypto.getRandomValues(new Uint8Array(16)), function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
  }
  function subject() {             // persistent anonymous id, created only when a grant is logged
    try {
      var k = 'legal_subject', v = localStorage.getItem(k);
      if (!v) { v = uuid(); localStorage.setItem(k, v); }
      return v;
    } catch (e) { return 'anon'; }
  }
  function forget() { try { localStorage.removeItem('legal_subject'); } catch (e) {} }
  function log(action) {           // only if the site has a backend endpoint: data-log="/api/consents"
    if (!d.log) return;
    var h = { 'content-type': 'application/json' };
    if (d.csrfHeader && d.csrfToken) h[d.csrfHeader] = d.csrfToken;   // frameworks with CSRF protection
    fetch(d.log, { method: 'POST', keepalive: true, headers: h,
      body: JSON.stringify({ subjectId: subject(), consentVersion: VERSION, formId: 'cookie-banner', channel: 'web', action: action }) })
      .catch(function () {});      // a failed log call must never break the page
  }
  function decide(a, m) {
    var was = read() || { analytics: false, marketing: false };
    var granted = (a && !was.analytics) || (m && !was.marketing);     // a category switched on
    var revoked = (was.analytics && !a) || (was.marketing && !m);     // a granted category withdrawn
    write({ v: VERSION, analytics: a, marketing: m, at: new Date().toISOString() });
    if (banner()) banner().hidden = true;
    if (granted) log('grant');     // a first-time refusal changes nothing, so nothing is logged
    if (revoked) log('revoke');
    if (!a && !m) forget();        // after log(): the id is read synchronously
    start(read());
    if (revoked) { purge(); location.reload(); }
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-consent]'); if (!t) return;
    var act = t.getAttribute('data-consent'), b = banner();
    function on(cat) { var i = b && b.querySelector('[data-consent-cat="' + cat + '"]'); return !!(i && i.checked); }
    if (act === 'reopen') { e.preventDefault(); if (b) b.hidden = false; }
    else if (act === 'accept') decide(true, true);
    else if (act === 'reject') decide(false, false);
    else if (act === 'save') decide(on('analytics'), on('marketing'));
  });
  var c = read(); start(c);        // counters can start at once; the banner needs the DOM
  ready(function () { if (!c && banner()) banner().hidden = false; });
})();
```
- Script attributes: `data-version` (consent text version), `data-ym` / `data-ga` / `data-gtm` (IDs; leave out what the site does not use), `data-log` (consent-log endpoint, only with a backend), `data-csrf-header` + `data-csrf-token` (when that endpoint is CSRF-protected).
- One rule everywhere: analytics counters (Metrica, GA, GTM) start only when `analytics` is granted; ad pixels (VK, Meta, TikTok) only when `marketing` is granted. A GTM container loaded early can fire any tag, so it is gated too; if the container holds ad tags, report it to the owner.
- Inline use (no-code platforms): the script reads its settings from its own tag, so keep the `data-*` attributes on the inline `<script>`; it waits for the DOM before showing the banner, so BODY-end or HEAD both work. Do not move the attributes to another element.
- Re-consent: a changed `data-version` makes `read()` return `null`, so the banner reappears and counters stay off until the new choice. The anonymous id is created in `localStorage` only when a grant is logged and removed when every category is off. Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
- Revoke: any element with `data-consent="reopen"` (footer link) shows the banner again; Reject after an earlier Accept purges cookies and reloads, because a loaded script cannot be unloaded.
- Other tags (chat widgets, maps, video embeds, social buttons): list them in the report if they load before consent; gate them through `start()` only when the knowledge pack says so.

## Consent banner
- Add the markup once per page (layout/partial for generators) with the site's classes and CSS variables; text per page language, copied from the documents step. Style `.cookie-banner` as a fixed bottom bar using the site's tokens; `[hidden]` must win (`.cookie-banner[hidden] { display: none; }`).
```html
<div id="consent-banner" class="cookie-banner" role="dialog" aria-live="polite" aria-label="[title]" hidden>
  <p>[banner text] <a href="/legal/privacy">[policy link text]</a></p>
  <button type="button" class="btn" data-consent="accept">[Accept all]</button>
  <button type="button" class="btn" data-consent="reject">[Reject]</button>
  <details>
    <summary>[Settings]</summary>
    <label><input type="checkbox" data-consent-cat="analytics"> [Analytics]</label>
    <label><input type="checkbox" data-consent-cat="marketing"> [Marketing]</label>
    <button type="button" class="btn" data-consent="save">[Save]</button>
  </details>
</div>
```
- Accept all sets `analytics` and `marketing`; Reject sets neither; the Settings view has two separate toggles, unchecked by default, and Save. Accept all and Reject use the same button class and size. Bump `data-version` when the texts change so the banner returns.

## Consent log (existing backend only)
- Static sites have no database. NEVER introduce a new database, BaaS or serverless function for this. Report the gap: consents live only in the visitor's browser; form notifications carry `consent_pd`, `consent_version` and a UTC time, which is a per-submission trace, not a complete log.
- If the site posts to the owner's existing backend with an ORM, follow the matching stack file there and set `data-log` on the script to that endpoint. Columns, append-only: `subject_id`, `created_at` UTC, `consent_version`, `text_sha256` (computed on the server from the known text), `channel`, `form_id`, `ip`, `user_agent`, `action`.
- Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`. `consent.js` sends exactly this. Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
- The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.

## Footer and links
Add Политика / Оферта / Возврат / Реквизиты to the footer on every page: edit the layout/partial for generators, every `.html` file for plain sites. Also place the policy link next to each consent checkbox and in the banner, plus a `data-consent="reopen"` link ("Cookie settings"). If the footer has a copyright line, extend it only to the short footer form of the owner's status (name, OGRN or OGRNIP where section 3.2 prints it, address, e-mail; INN only for a self-employed owner) from `.legal/answers.json`; never invent values. The owner details the footer shows (which requisites, by the owner's status) follow [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites).

## i18n
- Follow the site's scheme: parallel `/en/` pages, `data-i18n` JSON, or generator i18n (Hugo `i18n/*.toml`, Eleventy data files, Astro `src/i18n`). Put banner and checkbox strings where the other UI strings live.
- RU texts are authoritative. EN pages are translations: `lang="en"`, a visible notice at the top ("Translation for convenience; the Russian version prevails" in the site's language), and a `hreflang="ru"` link to the RU page.
- Single-language site: keep one language; add no switching machinery.

## Verify and record state
- Generators: `npm run build`, `hugo --gc --minify`, `bundle exec jekyll build`. Plain: serve with `python3 -m http.server 8000` and `curl -sI localhost:8000/legal/privacy.html | head -1` for each new page.
- `grep -rhoE 'href="/legal/[^"#]+"' --include=*.html . | sort -u` and confirm every target exists. `grep -L 'legal/privacy' $(find . -name '*.html' -not -path './legal/*' -not -path './node_modules/*')` lists pages still missing the footer link. Re-run the Detect grep: counter hosts must remain only in `consent.js`.
- In a browser with empty storage, no request to counter hosts before Accept; Reject then reload keeps it that way.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
