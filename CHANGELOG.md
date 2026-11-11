# Changelog

## [Unreleased]

Fixes from a review of 0.2.2.

### Scripts

- `check_docs.py` and `scan_repo.py` read files in windows-1251 and UTF-16 and files with a BOM instead of replacing their text: a legacy page with a leftover placeholder no longer passes as clean. A UTF-8 file with a few invalid bytes keeps its text, with those bytes replaced. `check_docs.py` adds a non-blocking `encoding` issue in each case.
- `check_docs.py` finds an INN or OGRN in a table, after bold marks or a dash, in HTML cells, after `&nbsp;`, as a pair `ИНН/ОГРН a/b` and under the capital Latin labels `INN`, `OGRN`, `OGRNIP`; a number followed by a year is no longer glued to it; a label never takes a number from across a blank line, a table rule row or the next table row; numbers in `answers.json` are compared without their grouping.
- A failed check digit blocks only on a public page: a draft keeps the number as the owner gave it, the page that needs it stays a draft.
- `report.py verify` leaves an `n_a` row of a requirement with a future date in `done`; `render` exits 2 on a `lang` that is not a string.
- `scan_repo.py` skips build output (`out`, `.output`, `.vercel`, `target`, `storybook-static`) and names the skipped build and vendor folders in `stats.skipped_dirs`; a component named after a legal page, a README and developer docs are no longer listed as legal pages.
- `scan_url.py` does not fetch links that may act when opened (logout, unsubscribe, delete, cancel, confirm, a token in the query) and lists them in `skipped`; it reads a quoted charset and sitemap entries with entities or CDATA.
- `rules.py` names no file that may be missing and prints no rule for a requirement the report rated `n_a`.
- `kb.py` takes `--kb` before the command too and reports an unwritable target without a traceback; offline whois stubs are found for Cyrillic domains.

### Workflow and stacks

- Stack guides install nothing: no `flutter pub get`, `pod install` or `expo prebuild`, `npx --no-install` everywhere, an Xcode or SwiftPM build only with packages already fetched; the WordPress consent log is a recipe for the owner's developer, not a table created on the site; paste artifacts are placed by the user.
- Project tests that need a database run only when its configured host is local.
- `owner.country` may be `null`: signs of a foreign owner found in recon are confirmed in the block before any registry lookup.
- An app with only a store listing and a bot without a repo run as `prod-only`: that one page is read, the platform's site is not crawled, and a live bot is never messaged.
- A passage left out for an unknown fact does not hold a page back, in every file that states the rule; mode `feature` skips the start gate and scans the code before `select.py`.
- One list of `state.json` kinds, `kb.py` in the scripts table, `bot` among the product kinds, `rkn` among the registry commands.

### Docs

- README: 14 eval scenarios and 30 trigger queries; English example prompts for the plan and feature modes.

## [0.2.2] - 2026-11-11

Fixes from a live run on a Tilda site with a foreign owner.

### Workflow

- A foreign owner: `egrul`, `npd` and `cbr` never run, the RKN operators registry is searched by name or handed to the user; drafts print the country and registration number in place of INN, OGRN and «по ЕГРЮЛ»; new `owner.reg_number` in `answers.json`; `check_docs.py` reports an OGRN label in a foreign owner's document and compares the registration number.
- `owner.withheld` holds only what the owner refused to give: «не выдумывай», «не знаю» or an unavailable owner leave the values `null`; texts that need no unknown value are still published, their policy link pointing to the existing policy page while the new one waits.
- The disputed sections of many cards may be written to `.legal/evidence/disputed-sections.md` and read card by card; every section is still read.
- The «Предложения скилла» row is written only when a proposal reached a public page, in SKILL.md as in report.md; a proposal left in a draft is listed in that draft's «Сделать вам» item.
- The no-repo step points to the no-code guide; the guide notes that `data-tilda-cookie-type` on counters does not show they wait for consent.

## [0.2.1] - 2026-11-04

Light package for skills.sh, workflow fixes from the evals.

### Scripts

- `scan_url.py` no longer fails to parse a page on Python 3.14 (its parser reused the name `_pending` that `html.parser` now keeps for its own buffer; found on a live Tilda site, whose home page lost its forms).

### Workflow

- Every assessed requirement gets the section «Пробелы и спорные места» of its card read before its status is set (`kb.py card` takes several ids); a detected feature the section calls disputed gets a `disputed` row.
- `report.py verify --select` requires a row for every applicable requirement (`uncovered_req`); the workflow passes `--select` in every mode and `evals/check_run.py` passes it when `.legal/evidence/select.json` exists.
- A row whose cited norm has no date in `norm_dates` takes the record's `effective_from`, not the date of another norm.
- A passage the template keeps only once a fact is confirmed (the storage region in the policy) is left out of the public page while the fact is unknown; the page is published and «Сделать вам» names the fact.
- Without python3: the shape of a hand-made `select.json`, the INN and OGRN check digits and the row table of the report are spelled out.

### Packaging

- The skill folder fits the text snapshot of skills.sh, which shows nothing for a skill that passes any of its limits (measured: about 200 files, about 512 KiB per file, 5–6 MB of text): 122 text files, 2.6 MB, none over 230 KB.
- The 227 requirement cards are one archive `references/jurisdictions/ru/cards.tar.gz` (members `cards/<slug>.md`, byte-identical to the former files); `scripts/kb.py` prints a card or one section, searches the cards, lists them and extracts them; without python3, `tar -xzOf cards.tar.gz cards/<slug>.md`.
- `requirements.jsonl` is split by direction into `requirements/A.jsonl` … `O.jsonl`; the records are unchanged. The scripts read the shards and ignore a `requirements.jsonl` left by an older install.
- Templates name a card by its id (`ru:<slug>`) instead of linking to a file.
- The generator writes the archive deterministically and leaves it untouched when its members did not change; `--check` compares members. Tests guard the snapshot budget, allow no other binary in the skill folder and scan the archive for private patterns.

### Tooling

- GitHub Actions: tests (with the leak check), script `--help` and the golden `check_run` on Python 3.9, 3.13 and 3.14 for every push to main and every PR.
- The runner is pinned to `ubuntu-24.04`: `ubuntu-latest` (26.04) has no Python 3.9 for `setup-python`.
- Tests run on Python 3.9: explicit ids for the registry failure cases; the stdlib-list check skips below 3.10.

## [0.2.0] - 2026-10-28

Bots as a product, plan and feature modes, rules library.

### Knowledge pack

- 227 requirements and cards (base date 2026-10-23); new direction O «Боты и мини-приложения в мессенджерах»: documents and consent in a chat bot, in-chat payments and receipts, personal data through a foreign messenger, three platform-rule records for Telegram and MAX; NUC security certificates (from 2027-03-01) and acquirers' root-certificate practice.
- Product kind `bot` (chat bots and mini apps in Telegram and MAX).

### Feature detection

- Catalog features `bot.telegram`, `bot.max`, `bot.mini_app`, `payments.bot_invoice`, `payments.telegram_stars`; stack id `bot` in `scan_repo.py`; feature-map links for them.

### Rules library

- `references/rules/`: 32 best-practice rules, one per file, each with the requirement ids it rests on and a basis (norm, practice, interpretation, platform rule); examples by stack.

### Scripts

- `select.py --planned` takes features in the owner's words; `feature_sources` says whether each feature was found, planned or both.
- `report.py`: mode `plan` with status `planned` and bucket `plan`, evidence `{owner}` and `{select}`, `verify --select`, `render --plan` for `.legal/plan.md`; `suggestions` («Что можно улучшить или добавить», «Критичного нет») and `plan_diff` («План и факт»); direction O.
- New `rules.py` renders `.legal/RULES.md` (at most 60 lines, deterministic, no absolute paths, labels never stronger than the requirements allow).
- `answers.json`: `product.planned_features`, `decisions.agent_rules_link`, `decisions.accepted_suggestions`.

### Workflow and stacks

- Modes audit, plan and feature (`references/workflow/plan.md`); the link line for the coding agent in `CLAUDE.md`, `AGENTS.md` or `.cursor/rules`; plan vs fact on a rerun; suggestions after every run.
- `references/stacks/bot.md`: documents, consent as two chat actions, receipt contact before the invoice, consent log for bots; platform rules for bots in applicability.

### Evaluation

- Evals 12 (Telegram bot shop), 13 (plan for an empty Next.js) and 14 (rerun with plan vs fact); 30 trigger queries.

## [0.1.0] - 2026-10-21

First release. Jurisdiction pack: Russian Federation (`ru`).

### Knowledge pack

- 219 requirements with full cards, base date 2026-10-16.
- 9 document templates with 322 elements (status and method per element), placeholders and forbidden clauses.
- 13 specs of documents without a template, owner questions and a registries guide.

### Feature detection

- Catalog of 78 features (signals in code, hosts and DOM).
- Map from features and owner facts to Russian requirements.

### Scripts

- 7 standard-library scripts: `scan_repo`, `scan_url`, `registry`, `select`, `check_docs`, `report` (verify and render) and the shared `_kb`.

### Workflow and stacks

- Skill `legal-kit`: phases 0 to 7 from intake to the report, 10 workflow guides.
- 10 stack guides: Next.js, React, NestJS, React Native, Flutter, Swift, Python, static HTML, generic web, no-code.

### Evaluation and tooling

- 11 eval scenarios with fixtures, offline registry stubs, 20 trigger queries and `check_run.py`.
- Eval results (small samples, graded by a model, details in the README): iteration 1, 75 of 98 expectations (77%) with the skill across 8 scenarios against 7 of 28 (25%) without it on 2 scenarios, 21 of 28 (75%) with the skill on those two; iteration 2, 24 of 28 (86%) on those two scenarios. The fixes made after iteration 2 were not run through the evals again.
- Deterministic knowledge generator `tools/build_knowledge.py` with `--check`.

### Packaging

- Claude Code plugin and marketplace manifests; install with `npx skills add maslakovSaveliy/legal-kit`.
- MIT license with a "Generated documents" clause.
