# Intake and owner dialogue (phases 0 and 3)

## Contents

- [Phase 0: intake](#phase-0-intake)
  - [Language](#language)
  - [Saved state](#saved-state)
  - [Facts from the prompt](#facts-from-the-prompt)
  - [Jurisdiction](#jurisdiction)
  - [Mode](#mode)
  - [Git tree](#git-tree)
  - [Start questions](#start-questions)
- [Phase 3: confirmation block](#phase-3-confirmation-block)
  - [Blocking and non-blocking items](#blocking-and-non-blocking-items)
  - [Document facts](#document-facts)
  - [Choosing the items](#choosing-the-items)
  - [Asking](#asking)
  - [Waiting or not](#waiting-or-not)
  - [Recording answers](#recording-answers)
  - [After the answers](#after-the-answers)
- [Without python3](#without-python3)

The questions themselves, their wording and the `answers.json` key of each one live in [owner-questions.md](../jurisdictions/ru/owner-questions.md). This file says when to ask and what to do with the answers.

The run stops for the user only here: after the start questions and, in phase 3, while a blocking item is open. Every other phase runs through; a question that comes up later goes to the report («Сделать вам»), never to a second block.

## Phase 0: intake

### Language

- The language of the user's message is the language of the dialog, the questions and the report (`lang` in `.legal/report.json`). `scripts/report.py render` knows `ru` and `en`: use `ru` for Russian, `en` for any other language, and write the chat summary in the user's own language.
- Legal documents are drafted in Russian whatever the dialog language ([documents.md](documents.md#language)).
- Russian legal terms stay in Russian inside English text when there is no exact equivalent: «оферта», «Сделать вам», «Спорно».

### Saved state

Read, if present:

1. `.legal/answers.json`: owner facts and decisions. Schema: [owner-questions.md, section «Схема answers.json»](../jurisdictions/ru/owner-questions.md#схема-answersjson). Keep every value it has; a run may only add newly learned values, correct a value the owner corrected, and refresh `updated`.
2. `.legal/state.json`: files the skill manages, with sha256. A non-empty `managed` list means this is a rerun ([ui-integration.md](ui-integration.md#reruns-and-statejson)).
3. `.legal/report.json`: the previous report, for the comparison in the final summary.

Never delete these files and never rebuild `answers.json` from scratch. If `answers.json` does not parse, stop and show the error; do not overwrite it.

On the first write create, unless they exist: `.legal/.gitignore` with the two lines `answers.json` and `evidence/`, and `.legal/sources.json` holding `[]` (`report.py verify --sources` needs the file).

### Facts from the prompt

Write what the prompt states into `answers.json` before any question, so nothing is asked twice. A value the prompt gives is never asked again, neither in the start questions nor in the confirmation block, where it is shown as confirmed:

| Prompt says | Key |
|---|---|
| product kind, name, what users do | `product.kinds`, `product.name`, `product.summary` |
| the production address, store pages | `product.urls`, `product.stores` |
| "code in the current folder" or a path; "no code" | `product.repo` (`.` or the path; `null` for no code) |
| owner name, status, INN, OGRN, address, e-mail, phone | `owner.*` (self-employed is `npd`, individual entrepreneur `ip`, company `ul`, foreign company `foreign`) |
| "I will not give the INN and OGRN yet", "do not invent them" | `owner.withheld`: the placeholder names, for example `["ИНН", "ОГРН_ИЛИ_ОГРНИП"]`; the values stay `null` |
| customers are consumers or businesses, minors, countries | `audience.*` |
| the owner names a regulated sector group as their own ("we are a licensed clinic, apply the medical rules") | `business.sectors`; a product description from which a group only follows is sector evidence for the confirmation block ([applicability.md](applicability.md#sectors)) |
| retention periods, hosting region, support hours, delivery or return terms | `document_facts` |
| "make the edits", "add what is needed" | `decisions.apply_changes: true` |
| "do not change anything", "only check" | `decisions.apply_changes: false` |
| "a consent checkbox at the form", «согласие у формы» | `decisions.consent_at_forms`: the form ids (as recon names them, for example `lead-form`) or `["*"]` for every form that collects data; phase 5 builds a consent checkbox there ([documents.md](documents.md#blocks-and-conditions)), and a rerun reads the list |

- A `localhost`, `127.0.0.1` or other local URL is a recon target for this run, never stored in `product.urls`: that list holds production addresses only.
- A fact the prompt does not state stays `null` (or keeps its saved value). Never fill it with a likely value: a name does not give a status, a domain does not give an owner.
- "Do not commit" needs no key: the skill never commits. `decisions.commit_legal_dir` stays `null` until the owner answers.
- Set `updated` to the current time in ISO 8601 UTC on every write.

### Jurisdiction

- The `ru` pack applies when the owner is registered in Russia or the product serves users in Russia (`audience.countries` contains `RU`), including a foreign owner serving Russian users.
- `owner.country` defaults to `RU` only when nothing points to another country. Signals of another country: a foreign legal form (GmbH, Ltd, Inc, LLC), a foreign address or registry number in the footer, a foreign ccTLD, prices only in a foreign currency, the interface only in another language. With such signals, the country is asked (start question 4), never assumed.
- If neither the owner nor the users are in Russia and the user needs another country's rules, say that this jurisdiction is not supported yet. Offer the technical inventory from recon (features, hosts, forms, cookies) without legal conclusions, draft no documents and stop.

### Mode

| Code available | Live URL available | `mode` in the report |
|---|---|---|
| yes | yes | `repo+prod` |
| yes | no | `repo-only` |
| no | yes | `prod-only` |

- Code is available when the working directory or the given path holds the product's source. The live URL is the production address or a URL the prompt gives for the running website (a local one included).
- Store listings are not a live URL: a mobile repo whose only pages are store listings is `repo-only`; the listings are still inspected ([recon-stores.md](recon-stores.md)).
- Without code and without a URL there is nothing to inspect: ask start question 2 or 3.

### Git tree

Before writing anything outside `.legal/`, note the state of the tree; the integration gate uses it ([ui-integration.md](ui-integration.md#gate)).

- `git status --porcelain --untracked-files=all -- . ':(exclude).legal'` prints nothing: the tree is clean.
- Changed or untracked paths that are all in `.legal/state.json` with a matching sha256 are the skill's own earlier edits and count as clean.
- Any other change, or no git repository at all: the tree is not clean; editing needs the user's explicit OK, which is a blocking item of the confirmation block.
- Baseline for the report: on a clean tree the start version of every file is git `HEAD`. Otherwise keep it yourself: before the run first changes a project file, copy the file as it was at intake to `.legal/evidence/baseline/<same path>` (excluded from git with `evidence/`), so rows about removed content can cite its lines ([report.md](report.md#evidence)).

### Start questions

Ask only on a first run and only when the prompt and `answers.json` together lack the product, the owner or a URL or repo.

- Take the questions from [owner-questions.md, section «Стартовые вопросы»](../jurisdictions/ru/owner-questions.md#стартовые-вопросы), at most 5, in one message, in the user's language.
- Ask only for keys that are still empty after the facts from the prompt are written. Drop every question the prompt or `answers.json` already answers:
  - what the product is (question 1), when there is code or a URL: recon shows it;
  - the address (question 2), when the prompt gives any URL, a local one included; a production domain is not a start question (if it matters, it is a non-blocking item of the confirmation block);
  - the repository (question 3), when the prompt says where the code is or that there is none.
- Never ask for passport data, Gosuslugi logins, passwords or codes, card data.
- Wait for the reply, write it into `answers.json`, then start recon.
- If the owner is still unknown after the reply (the user does not know or skips it), do not stop: continue with `null`, take guesses from the site's footer and legal pages and from WHOIS, and put them into confirmation items 1 and 3.

## Phase 3: confirmation block

One message after applicability ([applicability.md](applicability.md)), before any document or edit. There is only one.

### Blocking and non-blocking items

Blocking items change what the run applies or writes; the run waits while one is open:

- owner status (item 1);
- B2C or B2B (item 2);
- a sector, when sector evidence was found (item 4);
- minors (item 5);
- requisites the drafts will use, including the person responsible for personal data (item 3), and an INN or OGRN the registry did not find («ИНН … в ЕГРЮЛ не найден — проверьте»); a requisite the owner declines to give answers the item: its placeholder name goes to `owner.withheld`;
- applying edits (item 9) and, when the tree is not clean, editing over the user's changes;
- holding counters until consent (item 8), when a counter or SDK was found;
- document facts (item 10), only while a public page needs a fact marked «?» (nothing in recon shows it and it is not a business choice the skill may propose).

Every other item is non-blocking: revenue (item 6), the RKN notification (item 7), committing `.legal/` (the second question of item 9), document facts that all have a value from recon or a proposal, per-requirement questions. Phrase each as an assumption, «предполагаю: …; если не так, поправьте», and continue with that assumption.

### Document facts

Templates need business facts that are not requisites: retention periods per purpose, the region of the database and hosting, the processors and recipients with their names and countries, support hours, delivery terms, return methods, warranty, the support channel. Collect them in item 10 of the block, as one fill-in list, each line «что впишу — значение — откуда»:

1. Derive what recon shows: processors and recipients with their countries from the detected features and third-party hosts (`references/features/catalog.json`) and from env and config files; the hosting or database region from IaC, deployment config, a registry or WHOIS answer; the support e-mail and phone from the product itself. Name the source.
2. Propose a value where the fact is a business choice: «срок хранения заявок — 1 год после последнего обращения», «режим работы поддержки — пн–пт 10:00–19:00 МСК». Mark each «предложение, измените при необходимости». A proposal is a business default, never a norm: a period the law sets comes from the pack with its requirement id, not from a proposal.
3. Mark «?» what can be neither seen nor proposed (the actual database region with no sign in the code). Never fill it with a likely value.

The reply «да, как ты предложил» accepts every proposal. Write each value to `document_facts` under the placeholder name (`ИМЯ:цель` when a placeholder differs by purpose). Keep track of which values were proposals: every proposal that reaches a public page is listed in one report row for the owner to confirm or change ([report.md](report.md#proposals-of-the-skill)).

### Choosing the items

1. Start from [owner-questions.md, section «Блок подтверждения»](../jurisdictions/ru/owner-questions.md#блок-подтверждения).
2. Skip every item whose key already has a value given by the owner (`answers.json` from an earlier answer, or the prompt). Open the block with one line «Из вашего сообщения: …» that lists those values as confirmed, without a question; a registry answer that agrees with them joins that line («статус НПД подтверждён реестром»), one that differs is a mismatch item. Two exceptions: values this run wrote from an `ok` registry answer in phase 1 for keys the owner did not give are still shown in item 3 as guesses to confirm; and the sector item is asked when recon or a registry found evidence of a group that `business.sectors` does not list, even if `business.sectors` is `[]`.
3. Skip items whose answer cannot change this run: holding counters when no counter or SDK was found; applying edits and committing `.legal/` when there is no repo; revenue when the product takes no payments; the responsible person when no policy is drafted.
4. Add, if room is left, the per-requirement questions (owner-questions.md, section «Вопросы по требованиям») whose answer changes which documents are drafted or what they say. Choose among the ids `scripts/select.py` lists under `owner_questions`.
5. At most 10 items in total, blocking ones first; when room runs out, per-requirement questions go first, never item 10 while a drafted page needs a document fact. Everything else goes to the report, bucket `owner` («Сделать вам»).

### Asking

- Each item shows the skill's guess and where it comes from: the registry answer, the file and line, the page URL. Example: «По ЕГРЮЛ владелец — ООО "…", ИНН …. Верно?».
- A sector item names the evidence found («нашёл: ОКВЭД 86.23 в ЕГРЮЛ; слова "стоматология" в промпте»). A sector is never applied on a guess.
- Requisites taken from an `ok` registry answer are already in `answers.json` (phase 1) and are shown in item 3 as guesses: they are a valid source, but the owner may correct them, and a correction replaces them.
- The user answers "yes", "no" or a correction; one reply may cover all items.

### Waiting or not

- Wait while at least one blocking item is open. When none is open, send the message (if it has non-blocking items) and continue at once.
- Do not wait at all when the user said «просто сделай», "just do it" or "don't ask". Then:
  - a sector stays unconfirmed and is not applied; it goes to «Сделать вам» as a question;
  - requisites come only from the prompt, `answers.json` and `ok` registry answers; the rest stay placeholders in the drafts, and a public page that needs one stays in `.legal/drafts/` unless the owner withheld it ([documents.md](documents.md#drafts-and-public-pages));
  - document facts: recon values and proposals are taken, each listed in «Сделать вам»; «?» facts stay unknown;
  - `apply_changes` follows the prompt; if the prompt is silent, it is `true` on a clean tree and `false` otherwise;
  - `block_counters` is taken as `true`, the conservative choice, and the report says it was the skill's default;
  - every unconfirmed guess is listed in «Сделать вам».
- None of this relaxes the hard rules in SKILL.md.

### Recording answers

- Write every answer into `answers.json` under the key the item names, refresh `updated`. Confirmed sector groups go into `business.sectors` (any group of the feature map) and are not asked again on a rerun. Document facts go into `document_facts`; a requisite the owner declined goes into `owner.withheld` and leaves it when the owner gives the value later.
- `scripts/select.py` derives the owner facts from `answers.json` itself (`subject:<status>`, `b2c`, `minors`, `revenue_over_20m`, `domain_ru`, sectors; rules in owner-questions.md).
- If an answer changes applicability (a sector confirmed, a status corrected), rerun `scripts/select.py` before documents.

### After the answers

Right after the reply (or at once, when the block did not wait), before research and documents, without waiting for anything:

1. An INN or OGRN first given in the block runs the lookups keyed by it ([recon-prod.md](recon-prod.md#public-registries)): `egrul`; `npd` when the status is `ip` or `npd`; the RKN operators registry as a `manual` step for the report.
2. `ok` values fill the keys that are still `null` in `answers.json`. A value that differs from what the owner gave is not overwritten and is not asked again: it goes to the report as a mismatch («Сделать вам»), and the documents keep the owner's value.
3. `not_found` or `error` for a key the owner just gave: keep the owner's value, record the registry entry and add the check to «Сделать вам».
4. Rerun `scripts/select.py` if the new facts change applicability.
- Answers to per-requirement questions that have no key in the schema are not stored in `answers.json`; they go into the documents and the report rows they concern.

## Without python3

Nothing in these phases needs Python. Read and write the JSON files with any editor, keep the schema from owner-questions.md, and check the git tree with `git status --porcelain --untracked-files=all`.
