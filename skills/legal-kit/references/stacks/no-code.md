# No-code and CMS platforms (Tilda, WordPress, 1C-Bitrix)

Use when the site runs on a site builder or CMS. Often there is no repo and no admin access for the agent: then produce ready-to-paste artifacts and a numbered click-path for the owner, and never ask for or enter admin logins. With a repo (WordPress theme, Bitrix `local/` folder), edit files directly. The knowledge pack decides which forms need consent and which texts to show; this file shows the mechanics. Menu names change between versions: confirm each path in the live interface (marked "verify").

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- Tilda: page source contains `tildacdn.com`, `t-records`, `data-tilda-*`, `<div id="allrecords">`; blocks named `t###`. No repo; edits happen in the Tilda editor.
- WordPress: `/wp-content/`, `/wp-json/`, `<meta name="generator" content="WordPress ...">`; repo has `wp-config.php`, `wp-content/themes/<theme>/functions.php`, `wp-content/plugins`. Page builders: Elementor (`elementor-`), Gutenberg blocks (`wp-block-`), WPBakery. Forms: Contact Form 7 (`wpcf7`), Gravity Forms, WPForms, Elementor Forms. Shop: WooCommerce (`woocommerce`). Consent/analytics plugins: Complianz, Cookiebot, CookieYes, Site Kit, MonsterInsights: `wp-content/plugins` or the HTML source.
- 1C-Bitrix: `/bitrix/` assets (`/bitrix/js/`, `/bitrix/templates/`), `BX.` objects, header `X-Powered-CMS: Bitrix Site Manager`; repo has `bitrix/`, `local/`, `local/templates/<tpl>/header.php`, `/bitrix/php_interface/init.php`.
- Existing counters and widgets: scan the live HTML and network log (`scan_url.py` or a browser) for `mc.yandex.ru`, `googletagmanager`, `connect.facebook.net`, `vk.com/rtrg`, chat widgets, map and video embeds.
- Where deliverables go without a repo: `.legal/paste/<platform>/` (page HTML, loader script, banner markup, form settings checklist).

## Legal pages
- Existing route takes priority: search first (the live menu, footer, sitemap, the platform's page list) and update that page; never create a duplicate policy page. Defaults when none exists: `/legal/{privacy,offer,refund,requisites}`; where the platform cannot produce that path, use the nearest equivalent (below).
- Tilda: create a page for each document (Pages, New page, blank), add a text block or an HTML block (T123) with the document HTML from the documents step, set the page address (Page Settings, Address) to `legal/<slug>`; if the field rejects the slash use `legal-<slug>` (verify), publish. Keep the site's header/footer blocks and fonts. Owner action: publish all pages after the footer change.
- WordPress: Pages, Add New; paste the HTML into a Custom HTML block (or paragraphs/headings blocks), create a parent page with slug `legal` and make each document a child page of it (URLs `/legal/<slug>/`), publish. Assign the policy page in Settings, Privacy (core "Privacy Policy page" setting) so themes and forms link to it. Page builders: use their text/HTML widget inside the existing template.
- Bitrix: Content, Site Structure, Files and Folders: create `/legal/<slug>/index.php` (one folder per slug, for example `/legal/privacy/index.php`):
```php
<?php require($_SERVER['DOCUMENT_ROOT'] . '/bitrix/header.php'); $APPLICATION->SetTitle('[title]'); ?>
[document HTML]
<?php require($_SERVER['DOCUMENT_ROOT'] . '/bitrix/footer.php'); ?>
```
- All platforms: use the site template, not a standalone page, so header and footer match; add the URLs to the sitemap/SEO plugin the platform already uses; do not add `noindex`.

## Consent checkbox in forms
Unchecked by default, a separate field from the offer/terms checkbox, policy link next to it. Required (blocking submit) only for forms where the knowledge pack says consent is needed; otherwise leave it optional. After publishing, open each form and confirm the box is unchecked and the policy link works.
- Tilda: form block, Content, form fields: use the platform's agreement checkbox with the policy link (or add a Checkbox field with required on). Verify that "checked by default" is off.
- Contact Form 7: `[acceptance consent_pd] text [/acceptance]` in the form template (blocks sending when unchecked; `optional` flag makes it non-blocking). Gravity Forms: Consent field. Elementor Forms: Acceptance field, "Checked by default" off. WPForms: its agreement field or a required Checkbox. WooCommerce checkout: the "Terms and conditions" page setting is the offer checkbox; personal-data consent is a separate field:
Detect which checkout the store uses: the checkout page contains the Checkout block (editor shows "Checkout") or the `[woocommerce_checkout]` shortcode. The classic hooks below do not run on the block checkout (the default for new stores).
```php
// Checkout block: additional checkout field (WooCommerce 8.9+; verify the minimum version and whether the label accepts a link)
add_action('woocommerce_init', function () {
    if (!function_exists('woocommerce_register_additional_checkout_field')) return;
    woocommerce_register_additional_checkout_field([
        'id' => 'legal/consent-pd', 'label' => '[consent text]', 'location' => 'order', 'type' => 'checkbox',
        'required' => true,                       // false when this form does not need consent
        'error_message' => '[required message]',
    ]);
});
// Classic [woocommerce_checkout] shortcode
add_action('woocommerce_review_order_before_submit', function () {
    woocommerce_form_field('consent_pd', ['type' => 'checkbox', 'required' => true, 'label' => '[consent text]'], 0);
});
add_action('woocommerce_checkout_process', function () {   // required case only
    if (empty($_POST['consent_pd'])) wc_add_notice('[required message]', 'error');
});
```
- Bitrix: components with a consent option (`bitrix:main.feedback`, `bitrix:sale.order.ajax`, `bitrix:main.register`, web forms): set `USER_CONSENT` = `Y`, `USER_CONSENT_ID` to an agreement created under Settings, Product settings, User consents, and `USER_CONSENT_IS_CHECKED` = `N` (the default may be pre-checked; verify). Custom forms: plain `<input type="checkbox" name="consent_pd">` plus a server-side check.
- Forms the platform cannot extend (embedded third-party widgets, payment pages): note it in the report.

## Analytics gated by consent
Platform integrations (Tilda Site Settings, Analytics; WordPress analytics plugins; Bitrix counter settings) fire on every page load and cannot wait for a choice. Therefore:
1. Clear the counter ID from the built-in field / disable the plugin's injection (owner action, step-by-step in the report).
2. Load counters from the plain-JS loader `consent.js` of `static-html.md` (`data-ym`, `data-ga`, `data-gtm` attributes, banner markup, revoke link). If the platform cannot host files, paste the code inline: put the `data-*` attributes on that inline `<script>` tag itself (the loader reads them from its own tag and waits for the DOM before showing the banner, so BODY-end and HEAD both work; BODY-end is preferred).
- Tilda: Site Settings, More, HTML code insertion (end of BODY preferred, HEAD also works; verify names): paste the inline loader there, `data-*` attributes on its `<script>` tag. The banner markup goes into the footer page or a Zero Block placed on the footer page (Header and Footer settings) so it appears site-wide.
- WordPress (theme/child theme, or a code-snippet plugin if installed):
```php
add_action('wp_enqueue_scripts', function () {   // WordPress 6.3+ for the strategy argument
    wp_enqueue_script('legal-consent', get_stylesheet_directory_uri() . '/js/consent.js', [], '1', ['strategy' => 'defer', 'in_footer' => true]);
});
add_filter('script_loader_tag', fn ($tag, $handle) => $handle === 'legal-consent'
    ? str_replace(' src=', ' data-version="1" data-ym="12345678" src=', $tag) : $tag, 10, 2);
add_action('wp_footer', fn () => include get_stylesheet_directory() . '/legal/banner.php');
```
  If a consent plugin (Complianz, Cookiebot, CookieYes) is already installed, prefer its script-blocking categories for the counters and its banner; do not install a new plugin without the owner's approval.
- Bitrix: in `local/php_interface/init.php`, guarded because that file also runs on admin pages: `if (!(defined('ADMIN_SECTION') && ADMIN_SECTION === true)) { \Bitrix\Main\Page\Asset::getInstance()->addString('<script src="/local/js/consent.js" defer data-ym="12345678" data-version="1"></script>'); }`, or put that tag in the site template's `header.php` (admin pages do not use it). Move the banner markup into the template footer. Remove counters from `header.php`, include areas and the admin counter settings (verify where the site keeps them).
- Platform limits to put in the report when found: built-in statistics, chat/forms widgets, embedded maps/videos, payment pages, and plugins that inject their own scripts may still load before consent and cannot be gated from outside.

## Consent banner
Prefer the platform's existing consent component if it truly blocks counters (check the network log with empty storage). Otherwise use the banner from `static-html.md`, restyled with the site's own classes and fonts (Tilda: copy the colors/fonts from Site Settings; WordPress: theme CSS variables; Bitrix: template styles). Texts: from the documents step, in the site's language. Bumping `data-version` invalidates the stored choice and reopens the banner. Accept all and Reject get the same style and size; Accept all sets `analytics` and `marketing`, Reject sets neither, and the Settings view has two separate toggles, unchecked by default. A footer link "Cookie settings" (`data-consent="reopen"`) is the revoke path.

## Consent log (existing backend only)
- Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`. Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
- The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
- Do not build a log on these platforms. NEVER introduce a new database or external service. Describe what the platform already keeps and the gap: Bitrix stores accepted user consents for components that use the consent option (admin, User consents; verify); WordPress keeps nothing by default (Complianz/CookieYes-type plugins keep their own consent records; Contact Form 7 needs a storage plugin such as Flamingo to keep submissions); Tilda keeps form submissions (Leads) but no consent log.
- WordPress with owner approval and database access: a small `mu-plugin` creating an append-only `consent_log` table (via `dbDelta`) and a nonce-protected REST route that inserts rows, with fields `subject_id`, `created_at` UTC, `consent_version`, `text_sha256` (computed server-side), `channel` (`web`), `form_id`, `ip`, `user_agent`, `action` (`grant`/`revoke`); set `data-log` and `data-csrf-*` on the loader. Otherwise report the gap.

## Footer and links
- Tilda: Site Settings, Header and Footer: edit the footer page; add links to Политика, Оферта, Возврат, Реквизиты in an existing menu/text block, and keep the requisites text to the short footer form of the owner's status ([ui-integration.md](../workflow/ui-integration.md#footer-and-requisites); INN only for a self-employed owner), from `.legal/answers.json` only.
- WordPress: Appearance, Menus (classic) or Appearance, Editor, Patterns, Footer (block themes) or Widgets (footer areas): add the four pages to the footer menu.
- Bitrix: bottom menu (`.bottom.menu.php` in the site root, or the menu editor in the admin) and/or `local/templates/<tpl>/footer.php`.
- Also link the policy next to every consent checkbox and in the banner. Never invent owner data.

## i18n
- Tilda: a separate page set per language (for example `/en/privacy`) linked from the language switcher; RU pages are authoritative; each EN page starts with a visible translation notice.
- WordPress: the installed plugin (Polylang `pll__`, WPML string translation, TranslatePress) or `__('text', 'domain')` with `languages/*.po`; do not add a translation plugin. Bitrix: `lang/ru/...php` with `$MESS['KEY']` and `Loc::getMessage('KEY')`, English in `lang/en/`.
- Single-language site: keep one language.

## Verify and record state
- No build step. In a browser with empty storage, load the home page and a form page: no request to counter hosts before Accept, banner visible, Reject keeps it that way after reload; the checkbox is unchecked; all four footer links return 200. Counter host names may appear as strings inside the inline loader: judge by network requests, not by `grep` on the HTML.
- WordPress/Bitrix repos: `php -l` on every edited PHP file; `wp theme list` / `wp eval` only when WP-CLI is present.
- Artifacts without a repo: record the `.legal/paste/*` files in `.legal/state.json` `managed[]` (`path`, `sha256`, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`); repo files likewise. List owner actions (publish, clear built-in counter ID, assign pages) in the report. Do not commit.
