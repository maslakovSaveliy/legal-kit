# Applicability (phase 2)

## Contents

- [Inputs](#inputs)
- [Run select.py](#run-selectpy)
- [The feature map](#the-feature-map)
- [Sectors](#sectors)
- [Store rules](#store-rules)
- [Assess each requirement](#assess-each-requirement)
- [Dates and the roadmap](#dates-and-the-roadmap)
- [One package](#one-package)
- [Without python3](#without-python3)

This phase never waits for the user: open questions go to the confirmation block ([intake.md](intake.md#phase-3-confirmation-block)) or to the report.

## Inputs

- **Features:** the union of confirmed features from the code, the live site and the stores ([recon-repo.md](recon-repo.md#confirm-the-signals)). Ids come from `references/features/catalog.json`.
- **`.legal/answers.json`:** `select.py` derives everything else from it: owner status, business models, product kinds, owner facts (`subject:<status>`, `b2c`, `minors`, `revenue_over_20m`, and `domain_ru` when a host in `product.urls` ends in `.ru`, `.рф` or `.su`) and the confirmed sector groups in `business.sectors`.
- **Run date:** today, `YYYY-MM-DD`; the same date goes into the report's `generated`.

## Run select.py

```sh
python3 <skill>/scripts/select.py --kb <skill>/references/jurisdictions/ru \
  --answers .legal/answers.json --features <id,id,...> --today <YYYY-MM-DD> > .legal/evidence/select.json
```

No other flag is needed when the answers are passed. `--subject`, `--models`, `--products`, `--sectors` and `--facts` exist for runs without `answers.json`; an explicit flag replaces the value from the file. Output:

| Key | Content |
|---|---|
| `applicable` | `[{id, why, future_from}]`; `why` lists `always`, `feature:<id>`, `owner:<fact>`, `sector:<group>`; `future_from` is a date after the run date or `null` |
| `not_applicable` | `[{id, reason}]`: candidates filtered out by owner status, business model or product kind, or sectoral without a confirmed sector |
| `templates`, `template_reasons` | templates whose triggers in the feature map fired, and why (`always`, `feature:<id>`, `fact:<fact>`) |
| `documents` | specs `documents/<doc>.md` whose triggers fired: `[{name, path, why, requirements}]` |
| `owner_questions` | applicable ids that have facts code cannot show (`cannot_check`) |
| `not_detectable` | requirements no scanner or answer can establish, with what to ask the owner; they go to the report's `owner_checklist` ([report.md](report.md#reportjson)) |
| `warnings` | features or sectors missing from the map, unknown ids, a map without trigger sections |

Read `warnings`: a feature the map does not know brings no requirement; check it by hand against `requirements.jsonl` and, if a topic has no norm in the base, take it to research ([research-rules.md](research-rules.md)). Templates and documents are still candidates: documents.md confirms each one against its own trigger.

## The feature map

`references/jurisdictions/ru/feature-map.json`; its `_doc` explains the conventions.

| Key | Content |
|---|---|
| `always` | requirements of every product |
| `features` | catalog feature id to requirement ids |
| `owner_facts` | `subject:<status>`, `b2c`, `minors`, `revenue_over_20m`, `domain_ru` to requirement ids |
| `sectoral` | sector group to `{evidence, requirements}` |
| `not_detectable` | requirement id to why recon cannot establish it and what to ask |
| `platform_rules` | the store records |
| `templates`, `documents` | trigger sections `{name: {features, facts, always}}` that `select.py` uses to pick templates and document specs |

## Sectors

A sector requirement applies only when both hold:

1. **Evidence:** an entry of the group's `evidence` list in `feature-map.json` was found: `feature:<id>` (a catalog feature confirmed in code or on the site), `okved:<code>` (in an `ok` ЕГРЮЛ answer; matched by prefix, so `okved:86` matches 86.23), `licence:…` or `registry:…` (a licence or registry entry), or another confirmed group. A keyword feature alone is never enough.
2. **Confirmation:** the owner confirmed the group in the confirmation block (`owner_confirms` entries say what the owner must confirm), and it is in `business.sectors`. Any group of the map may be stored there, including owner statuses such as `social-network` or `telecom`; a stored group is not asked again on a rerun.

Evidence without confirmation: the group is a blocking confirmation item, not a row, even when `business.sectors` is `[]`. Confirmation without evidence (the owner says so): the owner's word is the evidence; note it. A word outside the evidence list, such as «консультации» in a design studio, is no sign at all: do not propose the sector and do not run sector registries. After the confirmation rerun `select.py`; the stored groups come from `answers.json`. `report.py verify --answers` rejects a `mandatory` or `conditional` row of a sector requirement (status other than `n_a`) that no stored group lists ([report.md](report.md#verify)).

## Store rules

The store records (`ru:pravila-storov-*`, listed under `platform_rules`) apply when `product.kinds` has `ios` or `android` or a store listing exists, whether `select.py` returns them through a feature such as `mobile.app` or you add them because of the listing. They are reported as platform rules: `source` `base`, `basis` `platform`, `level` `recommended` or `interpretation` ([recon-stores.md](recon-stores.md#store-rules-in-the-report)).

## Assess each requirement

For each applicable id read its record in `requirements.jsonl` (one line, `"id":"ru:<slug>"`):

- `trigger`, `summary`, `obligation`, `subjects`, `models`, `products`: does it really apply to this product; a feature can trigger a requirement whose condition the evidence does not meet.
- `tech[]`: what to look for in the product. Each item has `kind` `norm`, `practice`, `interpretation`, `inference` or `platform`; the kind of the item a row rests on becomes the row's `basis`.
- `cannot_check[]`: what only the owner knows; the matching short question is in owner-questions.md, section «Вопросы по требованиям».
- `norm_dates`, `effective_from`, `official_urls`, `source_kind`, `legal_confidence`: the row's norm, dates, sources and the ceiling of its level ([report.md](report.md#level-and-basis)).
- `templates`: the documents that implement it.

Open `cards/<slug>.md` only when the record is not enough: an ambiguous trigger, a disputed point, the exact periods or wording a document needs.

Then set the status:

| Status | When |
|---|---|
| `present` | evidence shows it is met (after this run's edits, the new lines count) |
| `missing` | evidence shows it is not met |
| `partial` | met in part, or seen only statically («JS не выполнялся») |
| `not_visible` | code, site and registries cannot show it (a `manual` registry, facts only the owner knows); bucket `owner` |
| `n_a` | it does not apply; the row says why (nothing is sold, revenue below the threshold, no sector sign) |

For personal-data consent the status follows the basis chosen per form ([documents.md](documents.md#blocks-and-conditions)): the template's fork table decides, except that an explicit wish of the user for consent at a form (`decisions.consent_at_forms`) makes consent the basis of that form.

Report `n_a` rows for requirements the user asked about or would expect (an offer and returns when nothing is sold, payment thresholds, sector rules ruled out); the other filtered ids stay in `.legal/evidence/select.json`.

## Dates and the roadmap

- `effective_from` of a row is always one of the requirement's own dates (`norm_dates[].from` or `effective_from`); `report.py verify` rejects any other date.
- A record whose `effective_from` is a single date after the run date: one row, bucket `roadmap`, with that date.
- A record whose `effective_from` is `mixed` and whose `norm_dates` include both passed and later dates: its row covers what is in force, with `effective_from` set to the latest passed date; the later part gets its own row with `req` `null`, the id and the date in the title, level `recommended` or `interpretation`, bucket `roadmap`, `effective_from` the future date. A requirement id is never used in two rows, except a separate `disputed` row about a detected feature next to a norm-based row ([report.md](report.md#evidence)).
- A row whose `effective_from` is `null` inherits the requirement's latest date in `report.py verify`; set `effective_from` on every row of a requirement that has a future date, and on any row whose cited norm has a date in `norm_dates` ([report.md](report.md#rows)).

## One package

- A mixed product (goods and services, subscription and consultations) is the union of its features: each requirement once in the report, with all its evidence in that one row.
- Documents are merged the same way: one policy, one personal-data consent text, one banner; two offers only when goods and services both exist ([documents.md](documents.md#which-documents)).

## Without python3

Do what `select.py` does by hand, with the files under `<skill>/references/jurisdictions/ru/`:

1. Owner facts from `answers.json`: `subject:<owner.status>`; `b2c` if `audience.b2c` is true; `minors` if `audience.minors` is `14-18` or `under-14`; `revenue_over_20m` if true; `domain_ru` if a host in `product.urls` ends in `.ru`, `.рф` (`.xn--p1ai`) or `.su`.
2. Collect candidate ids from `feature-map.json`: `always`, plus `features[<id>]` for each confirmed feature, plus `owner_facts[<fact>]` for each fact, plus `sectoral[<group>].requirements` for each group in `business.sectors`.
3. For each id find its line: `grep -F '"id":"ru:<slug>"' <skill>/references/jurisdictions/ru/requirements.jsonl`. Drop it when the owner status is not in `subjects`, or neither model in `models`, or no product kind in `products` (an empty list means no restriction), or its `obligation` is `sectoral` and no confirmed group lists it.
4. `future_from`: the latest date among `norm_dates[].from` and `effective_from`, if it is after the run date.
5. Templates and documents: a name in the map's `templates` or `documents` section applies when it has `always`, or one of its `features` was found, or one of its `facts` (owner facts and confirmed groups) holds.
6. `not_detectable`: entries of the map's `not_detectable` whose id is not already a candidate and fits the owner, model and product filters.
