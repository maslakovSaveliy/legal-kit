# UI integration (phase 6)

## Contents

- [Gate](#gate)
- [Design inventory](#design-inventory)
- [Stack guides](#stack-guides)
- [Legal pages and routes](#legal-pages-and-routes)
- [Consent checkbox](#consent-checkbox)
- [Counters and the banner](#counters-and-the-banner)
- [Consent log](#consent-log)
- [Footer and requisites](#footer-and-requisites)
- [i18n](#i18n)
- [Reruns and state.json](#reruns-and-statejson)
- [Verify](#verify)
- [No repo or a no-code site](#no-repo-or-a-no-code-site)
- [Without python3](#without-python3)

This file says what to build and the rules; each stack guide says how. The documents' texts come from phase 5. This phase never waits for the user: what cannot be done goes to the report.

## Gate

Edit the repo only when all hold:

- `decisions.apply_changes` is `true` (from the prompt or the confirmation block);
- the tree was clean at intake, or the user agreed in the confirmation block to edit over their uncommitted changes ([intake.md](intake.md#git-tree));
- there is a repo. Without one, see [No repo or a no-code site](#no-repo-or-a-no-code-site): those artifacts are produced whatever `apply_changes` says, because they change nothing of the user's.

Otherwise make no repo edits: the drafts stay in `.legal/drafts/` and each fix becomes a step in «Сделать вам». Never commit, push, stash, reset or delete files.

Scope of the edits:

- Build only what an applicable row needs: no banner or loader without a counter or SDK, no checkbox without a form that collects data, no page for a document that was not drafted. A product that needs only an owner block in the footer gets only that.
- Never remove or silently rewrite the product's own features, widgets, embeds or marketing wording to resolve a finding (a foreign login widget, a "certificate" promise on a course page): report it and let the owner decide. Legal pages and forbidden offer clauses are the exception ([documents.md](documents.md#existing-legal-pages)).
- A configuration file the repo does not have (for example `Info.plist`) is never invented: the setting becomes a manual step in «Сделать вам».

## Design inventory

Before writing UI, know what the project already has. Start from `design` in the repo scan, then open the files:

- root layout and the layout of an existing content page; the footer component;
- UI kit and components: button, checkbox, switch, dialog or sheet, link;
- design tokens: CSS variables, Tailwind theme, theme files in mobile apps;
- the form library and validation (react-hook-form, Formik, Django forms, class-validator DTOs, SwiftUI state);
- i18n library and catalogs; the routing convention and existing legal routes;
- without a repo: the screenshots from prod recon.

Rules: reuse these components, tokens, catalogs and conventions. Add no package of any kind (UI kit, CSS framework, font, Markdown package), no database and no ORM. The only exception is a package a stack guide explicitly allows, such as Flutter's first-party `url_launcher` when nothing in the app can open a URL: add it to the manifest (`pubspec.yaml`) only, do not install it, and mention it in the report. Never install or upgrade dependencies.

## Stack guides

Use the guide of every stack in `stacks` of the repo scan; a NestJS backend with a React frontend uses both.

| Stack id | Guide |
|---|---|
| `nextjs` | [nextjs.md](../stacks/nextjs.md) |
| `react` | [react.md](../stacks/react.md) |
| `nestjs` | [nestjs.md](../stacks/nestjs.md) |
| `react-native` | [react-native.md](../stacks/react-native.md) |
| `flutter` | [flutter.md](../stacks/flutter.md) |
| `swift` | [swift.md](../stacks/swift.md) |
| `python` | [python.md](../stacks/python.md) |
| `static-html` | [static-html.md](../stacks/static-html.md) |
| `generic-web` | [generic-web.md](../stacks/generic-web.md) (Vue, Nuxt, Svelte, Angular, PHP and others) |
| `no-code` | [no-code.md](../stacks/no-code.md) (Tilda, WordPress, 1C-Bitrix) |

Each guide has the sections Detect, Legal pages, Consent checkbox, Analytics gated by consent, Consent banner, Consent log, Footer, i18n, Verify.

## Legal pages and routes

- An existing route for the same document has priority: update that page in place ([documents.md](documents.md#existing-legal-pages)).
- Otherwise use `/legal/privacy`, `/legal/offer`, `/legal/refund`, `/legal/requisites`, created only for documents that were drafted. Other documents take a slug under `/legal/` the same way.
- A page is built only from a draft with no unresolved `{{…}}` other than requisites in `owner.withheld` ([documents.md](documents.md#drafts-and-public-pages)). A draft that still misses a document fact or a requisite stays in `.legal/drafts/`: no route, no footer link to it, and a «Сделать вам» item naming the missing values. The same holds for paste artifacts.
- Pages use the layout of an existing content page, are reachable without login and are not hidden from search.
- Mobile apps do not bundle document texts: a Documents screen (or the About screen) opens the hosted URLs, kept in one constants file, and is linked from settings and from every form that collects data.
- A mobile app without a website has nowhere to host them: write the pages to `.legal/paste/html/`, keep the constants as clearly marked TODO values, and add a «Сделать вам» item: publish the pages and put their URLs into the constants file.

## Consent checkbox

Build exactly what the documents phase chose for each form ([documents.md](documents.md#blocks-and-conditions)):

- When the user explicitly asked for consent at a form (`decisions.consent_at_forms`), that form gets the consent checkbox below, even where the template allows a notice; the report records that the owner asked for it.
- **Notice** (the basis is the contract): a line at the submit button with a link to the policy; no checkbox. The report offers the consent checkbox as the alternative in «Спорно».
- **Consent checkbox** (the basis is consent): its own field with its own name (`consentPd`, `consent_pd`), unchecked by default, separate from accepting the offer or terms, from other consents and from unrelated options such as "save address"; the policy link sits outside the clickable label.
- When consent is required for the form, the submit stays disabled until the box is ticked and the server rejects a request without it; when it is optional, it blocks nothing.
- Use the project's checkbox component and form library; one checkbox component for the whole product, reused by every form.
- Distribution consent (public reviews with a name or photo) is its own checkbox at the publish action.

## Counters and the banner

When counters or SDKs exist and `decisions.block_counters` is `true`:

- move every counter and SDK start behind consent: the counter loads, or the SDK activates, only after the visitor allows analytics; keep the counter ids in the loader or config; nothing fires with empty storage;
- add a banner (mobile: a first-launch sheet) built from the project's components, with Accept and Reject of equal size and prominence on the first layer, a link to the policy and, where needed, separate switches for analytics and marketing, off by default;
- add a footer link or a settings entry that reopens the choice;
- promotional channels (marketing push, e-mails) wait for marketing consent when the requirement records ask for it; the OS notification permission is not that consent.

Holding counters until consent is engineering practice, not a norm: its report row has `basis` `practice` and level `recommended` or `interpretation`. When `block_counters` is `false`, leave the counters as they are and report the owner's decision.

## Consent log

- Only on an existing backend with a database and ORM. Never create a backend, a database, an ORM or a new service.
- Append-only: one model or table and one service with a create method; no update or delete path.
- The table is named `consent_log` in every ORM, as in the stack guides: Prisma `@@map("consent_log")` with `@map` on snake_case columns, TypeORM `@Entity('consent_log')`, Django `Meta.db_table = "consent_log"`, SQLAlchemy `__tablename__ = "consent_log"`, Laravel `Schema::create('consent_log', …)`.
- Payload `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`. Log only grants and revocations of an earlier grant; never log a first-time refusal.
- Store the hash of the exact consent text for its version, the time in UTC, and the IP and user agent only as the stack guide allows.
- **Migrations.** Never apply a migration to any database: no `migrate`, `migrate deploy`, `db push`, `alembic upgrade`, `typeorm migration:run`. Every model the run adds or changes (the log, new fields on an existing model) gets a migration file by one of these routes:
  - a generator that does not connect to the database: `python manage.py makemigrations`;
  - a generator that does connect (`prisma migrate dev --create-only --name add_consent_log`, `typeorm migration:generate`, `alembic revision --autogenerate`), only when the database host configured in the project is `localhost`, `127.0.0.1`, `::1` or a local socket. The host is read from the connection string in `.env`, the config or the schema, host only: never print or copy the credentials. Any other host, no configuration or an unreadable one: do not run it;
  - otherwise (the generator may not run, dependencies are not installed, no database) write the migration by hand only where the ORM's format is plain and stable, matching the model exactly:
    - Django: `<app>/migrations/<next number>_<name>.py` with `migrations.CreateModel` or `AddField`, depending on the app's latest migration (`0001_initial.py` and an empty `__init__.py` for a new app);
    - Alembic: a revision file in the versions folder whose `down_revision` is the current head;
    - Laravel: `database/migrations/<YYYY_MM_DD_HHMMSS>_create_consent_log_table.php`;
    - Prisma: `prisma/migrations/<YYYYMMDDHHMMSS>_add_consent_log/migration.sql` with the SQL that creates the mapped table, columns and index for the schema's datasource provider (plus `migration_lock.toml` with that provider when the folder is new);
    - any other ORM (TypeORM, Drizzle, Mongoose and the like): no hand-written file.
- Whichever route was taken, put the exact command in «Сделать вам» (generate or check the migration, then apply it on the development database), and record the files with kind `consent-log`.
- No backend (a mobile app or static site only): no log; report the gap with the field list for the backend team.
- The log itself holds personal data: the policy draft lists it as a processing purpose.

## Footer and requisites

- Two forms of the owner block, both from the template `svedeniya-o-prodavce-i-vladelce-sayta`. The **requisites page** follows section 3.1 (full): for the owner's status every element that the element table (`elements.json`) requires for the requirements that apply («обязательно», or «при условии» when the condition holds), with the identifiers the status variant prints (INN, OGRN or OGRNIP): for any site the name, the address and the e-mail; for a seller also the phone where the element names it, registration and licence data and the working hours. The **site footer** follows section 3.2 (short footer) and links to that page: the owner's name, the OGRN or OGRNIP where 3.2 prints it, the address and the e-mail; by status: ООО name (OGRN optional), ИП full name and OGRNIP, self-employed full name and INN (what a self-employed owner publishes is the owner's decision, see the third bullet), a foreign company name and country of registration. The footer prints no INN for an ООО or an ИП and nothing else the short form lacks; INN, registration data, licence and working hours live on the requisites page. On mobile the About or Documents screen follows section 3.4. Values come exactly from `answers.json` (`owner`, `document_facts`); nothing is added from memory.
- A requisite the owner withheld (`owner.withheld`) stays a visible placeholder in the block, with a «Сделать вам» item. Any other unknown value is asked in the confirmation block; the block never shows it as a placeholder.
- An element whose content the card leaves open for the status (what a self-employed owner publishes as name, address or other identifiers) is the owner's decision: publish only what the product already shows or the owner confirmed for publication, and report the rest as a question, never as a placeholder.
- Links to every legal page that exists, added to the footer's existing link list.

## i18n

- With catalogs: every UI string is a key in every locale the project has (for example a `Legal` namespace): banner and checkbox labels, notices, footer labels and owner-block captions, link texts, page titles, the translation notice. No hard-coded labels in components.
- Long legal documents may live in content files per locale (Markdown, MDX or a `ts`/`json` module per document and locale, as the stack guide renders prose) instead of the catalogs; their titles and the links to them are still catalog keys.
- Russian strings and documents are authoritative; English legal pages render a translation notice key at the top.
- Without catalogs: write the strings in the language of the surrounding UI.

## Reruns and state.json

`.legal/state.json` is `{"managed": [{"path", "sha256", "kind"}]}`, one entry per path created or edited by the skill, with the sha256 of its final content.

| `kind` | Files |
|---|---|
| `page` | legal pages, their routes, the Documents screen and its URL constants |
| `checkbox` | forms and server-side validation of consent |
| `banner` | banner, consent store or loader, gated analytics and SDK wrappers, native config flags |
| `footer` | footer, layout requisites, links |
| `consent-log` | log model, migration, service, endpoint |

Catalogs and other shared files take the kind of their main change. On a rerun:

- a managed path whose sha256 equals the file on disk belongs to the skill: update it in place;
- a different sha256 means someone edited it: leave it untouched and list it, with the difference, in the report («Сделать вам»);
- before inserting a checkbox, banner, footer block, route or log model, look for one that already exists (by path in `state.json` and by searching the code) and update it instead;
- a rerun with nothing new changes no project file; only the dated report is rewritten;
- keep one entry per path, refresh each sha256 after the last edit (`shasum -a 256 <file>` or `sha256sum <file>`), and keep entries of earlier runs.

## Verify

1. Run the project's own checks from the stack guide's Verify section that can run as the project stands: typecheck, lint, build, tests, with the lockfile's package manager. Install nothing. When dependencies are not installed, add «build not run: dependencies not installed» and the install command (for example `npm ci`) to `not_checked`.
2. Fix every failure the edits caused. A failure that existed before the run is reported, not "fixed" by unrelated changes.
3. Run `scripts/check_docs.py` with the drafts and, each after its own `--public`, every page and project file the run created or edited outside `.legal/` plus the paste artifacts ([documents.md](documents.md#check-the-drafts)); it must exit 0. Fill a blocking placeholder from `answers.json`, turn a runtime one into the project's interpolation; if the value is unknown, undo this run's change to that file, keep the draft and add a «Сделать вам» item.
4. Repeat the Detect grep: counter calls appear only inside the gated loader. With a dev server and a browser, load the page with empty storage and confirm no request to counter hosts before Accept.
5. Show `git status` and `git diff --stat`; leave everything uncommitted.

## No repo or a no-code site

- Write paste-ready artifacts to `.legal/paste/<platform>/` (`tilda`, `wordpress`, `bitrix`, or `html` for any other site): page HTML, the banner and loader snippet, form settings, footer block. Match the site's look from the prod screenshots.
- Give numbered placement steps in «Сделать вам», following [no-code.md](../stacks/no-code.md) for the platform's menus.
- Use computer use or the user's browser to place them only if the user asks; the user logs in, the skill never asks for or types admin passwords.
- Record the artifacts in `state.json` like project files.
- They are produced even when the user said not to change anything: they live in `.legal/` and change nothing of the user's.

## Without python3

Nothing in this phase needs Python. Compute sha256 with `shasum -a 256`, `sha256sum` or `certutil -hashfile <file> SHA256`.
