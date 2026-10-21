# Changelog

## [Unreleased]

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
