# Plan and feature modes

## Contents

- [Choosing the mode](#choosing-the-mode)
- [Features in the owner's words](#features-in-the-owners-words)
- [Plan mode](#plan-mode)
- [plan.md](#planmd)
- [RULES.md](#rulesmd)
- [Link for the coding agent](#link-for-the-coding-agent)
- [Feature mode](#feature-mode)
- [Plan vs fact on a rerun](#plan-vs-fact-on-a-rerun)
- [Suggestions after the run](#suggestions-after-the-run)
- [Without python3](#without-python3)

The audit (`repo+prod`, `repo-only`, `prod-only`) checks what exists. The two modes here put the requirements in front of the code before it is written: `plan` for a product that does not exist yet, `feature` for one function being added now. Norms, levels and evidence rules stay the same; a rule that is an interpretation, a practice or a platform rule is never presented as an obligation.

## Choosing the mode

Decide in phase 0, from the words of the request first and the project second.

| Mode | When | Output |
|---|---|---|
| audit (`repo+prod`, `repo-only`, `prod-only`) | a product exists: code with features or a live URL; the request is to set up, check or audit | the usual run ([intake.md](intake.md#mode)) |
| `plan` | no code, or the scan finds no features and no legal pages; or the request says «создаю», «новый проект», «до разработки», «перед запуском», "new project", "build checklist"; or the owner gives a spec or mockups | `.legal/plan.md`, `.legal/RULES.md`, drafts in `.legal/drafts/`, `report.json` with `mode: "plan"` |
| `feature` | an existing project gets one function now: «добавляю оплату», «делаю форму заявки», «пишу бота» | the rules for that function in the chat; `.legal/RULES.md` rebuilt when it exists or is asked for; no report |

- Plan requested, but the scan found features: say in one line that code already exists and offer the audit; do not write a plan over a working product without the owner's word.
- The mode is recorded in `report.json` (`mode`). The feature mode writes no report.

## Features in the owner's words

- Map the description to `references/features/catalog.json` by `title_ru`, `title_en` and `notes`. Keep a short quote of the owner (up to 25 words) for each feature.
- Store them in `product.planned_features` of `answers.json` as `{"id", "quote"}` ([owner-questions.md](../jurisdictions/ru/owner-questions.md#схема-answersjson)).
- An ambiguous phrase («приём заявок» — a form or a chat?) becomes a «предполагаю: …» item of the confirmation block.
- A function the catalog does not cover goes to `not_covered` of `report.json` and to the plan as «не покрыто каталогом», with no requirement attached. Never invent a feature id.
- `select.py` takes them only through `--planned`; it never reads them from `answers.json`. The audit does not pass `--planned`.

## Plan mode

1. Phase 0: the usual intake, mode `plan`; facts and planned features from the prompt go to `answers.json` at once.
2. Phase 1: recon of what exists (an empty repo, a spec, mockups). Features found in code go to `--features` as usual.
3. Phase 2: `select.py --planned <ids> [--features <ids>] --answers .legal/answers.json --today <date> > .legal/evidence/select.json`.
4. Phase 3: the confirmation block, at most 10 items, nothing already in the prompt. «Применять правки?» and «Коммитить `.legal/`?» are not asked: there is no code. Instead, only when `CLAUDE.md`, `AGENTS.md` or a `.cursor/rules/` folder exists, ask whether to add the link line ([below](#link-for-the-coding-agent)); `decisions.agent_rules_link`. Ask about holding counters when analytics is planned.
5. Phase 5: drafts from the templates in `.legal/drafts/` as usual ([documents.md](documents.md#drafts-and-public-pages)). Unknown requisites stay placeholders; there are no public pages.
6. Phase 6 is skipped: without code nothing is integrated.
7. Phase 7: `report.json` with `mode: "plan"`, then `report.py verify --select .legal/evidence/select.json`, `render --plan`, `rules.py` and a short chat summary ([report.md](report.md#plan-mode)).

## plan.md

`report.py render .legal/report.json --plan > .legal/plan.md` builds it from the rows. Sections, in order:

1. header: product, date, base date, «Не юридическая консультация»;
2. «Что запланировано»: the features with the owner's quotes; «не покрыто каталогом»;
3. «Страницы и документы» (`topic: pages`): what is needed and where the draft lies;
4. «Согласия» (`consent`): a separate unticked checkbox, apart from the offer; in a bot, two actions in the chat;
5. «Что грузить только после согласия» (`gating`): counters, pixels, SDKs;
6. «Оплата, подписки, автосписания, чеки» (`payments`);
7. «Реквизиты» (`requisites`): footer and a separate page; unknown values stay placeholders;
8. «Прочие требования» (`other`);
9. «Нормы, которые вступят позже»: `roadmap` rows with their dates;
10. «Сделать вам и спорно»: `owner` and `disputed` rows;
11. «Что можно улучшить или добавить» ([suggestions](#suggestions-after-the-run)).

Every item names its requirement id, its level and its basis (norm, practice, interpretation, platform rule). «обязательно» appears only at `mandatory` rows.

## RULES.md

One canonical rebuild in every mode. `RULES.md` is for the code still to be written, so it needs the planned features too, which the audit's own `select.json` does not have:

1. `select.py --planned <ids of product.planned_features> --features <found ids> --answers .legal/answers.json --today <date> > .legal/evidence/select-rules.json` (in mode `plan` the run's `select.json` already is this file);
2. `rules.py --select .legal/evidence/select-rules.json --stacks <stack ids> --lang <lang> --today <date> [--report .legal/report.json] > .legal/RULES.md`, with `--report` whenever `.legal/report.json` exists (after `report.py verify` exits 0), so a requirement the run rated `interpretation` is never «норма».

- It picks the rules of `references/rules/` ([the library](../rules/README.md)) whose requirements are applicable and whose features were found or planned, at most 60 lines.
- A line: `- <rule> — <requirement ids>, <label>; как: legal-kit references/stacks/<stack>.md`. The label is never stronger than the requirements allow, nor than the level the run gave the row in `report.json`: a requirement the run rated `interpretation` (for example consent under a contract basis) is never «норма».
- No absolute paths: the file can be committed and works for colleagues.
- Two header lines say that the file is generated and point to `plan.md` and the report.
- The output is deterministic; a rerun with the same inputs gives the same bytes, so `state.json` can compare its sha256.
- Record it in `.legal/state.json` with `kind` `rules`. A `RULES.md` whose sha256 no longer matches was edited by the owner: leave it and list it in the report.
- In the audit `RULES.md` is written too when it already exists or the owner asks for it.

## Link for the coding agent

- Only with `decisions.agent_rules_link: true`.
- An existing `CLAUDE.md` or `AGENTS.md` gets one line in the project's language: `Юридические правила проекта: .legal/RULES.md` or `Legal rules of the project: .legal/RULES.md`. Nothing else in the file changes.
- An existing `.cursor/rules/` folder gets one new file `legal-kit.mdc` with the same line.
- None of them exists: create nothing; the line goes to «Сделать вам».
- Record each in `state.json` with `kind` `agent-link`; a rerun finds the line and does not add a second one.

## Feature mode

1. Map the function to the catalog, one quote per feature.
2. Read `answers.json` when it exists. When it does not, ask nothing: take the facts from the prompt and mark the rest «предполагаю: …». Create `.legal/answers.json` (only `product.planned_features` and the prompt's facts, the rest `null`), `.legal/.gitignore` and `.legal/sources.json`.
3. Run `select.py --planned <ids> --features <found>` so the rules see what exists, for example the consent mechanism.
4. Give the rules of this function in the chat, with links to the sections of the stack guide. When the agent writes the code in the same session, it writes it by these rules.
5. Rebuild `.legal/RULES.md` by the canonical rebuild ([RULES.md](#rulesmd)), with `--report` when `.legal/report.json` exists, when it exists or the owner asks; update `state.json`.

It asks at most one question, and only when a rule cannot be chosen without the fact (B2C or B2B for a payment). It writes no `report.json` and edits no legal page. At the end it offers a full audit when `answers.json` has no owner or the last report is older than 90 days. The next audit shows the function as `planned_not_found` until it appears in the code.

## Plan vs fact on a rerun

When `product.planned_features` is not empty, the audit compares it with what recon found:

- `planned_not_found`: planned, not found in the code or on the site; it goes to the suggestions with the requirement ids of the feature;
- `found_not_planned`: found, not planned; adding it to the plan is an item of the confirmation block (item 10), with the quote «найдено в коде, <file>».

`report.json` carries them as `plan_diff`; `render` prints «План и факт». Answers come from `answers.json`, so no question is asked again; `RULES.md` is rebuilt by the canonical rebuild ([RULES.md](#rulesmd)) for the planned and the found features together, with `--report`, without duplicates.

## Suggestions after the run

Every run except the feature mode ends with «Что можно улучшить или добавить»: `suggestions` in `report.json`, at most 7 items, and a short block in the chat.

- An item: what to do, why (requirement id or «практика»), level `recommended` or `interpretation`, effort `small` or `work`, `auto` when the skill can do it on a rerun.
- Sources: `recommended` and `interpretation` rows not done, future norms, disputed points with a safe variant, map notes (for example the acquirer's root certificate), consent UX, a missing `RULES.md`, `planned_not_found`.
- Risk first, then convenience. With nothing substantial say so: an empty list renders as «Критичного нет».
- Suggestions never raise an obligation level and are never applied without the owner's answer. Accepted ones go to `decisions.accepted_suggestions` and are not offered again.

## Without python3

- Mode: decide by the table above.
- Planned features: write them into `answers.json` by hand and select requirements through the feature map as [applicability.md](applicability.md#without-python3) describes, treating planned features like found ones.
- `plan.md`: write the sections of [plan.md](#planmd) from the rows yourself.
- `RULES.md`: take the rules of `references/rules/` whose requirements apply and whose features match, lowest label of rule and requirement, at most 60 lines, no absolute paths.
