# Changelog

## [Unreleased]

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
