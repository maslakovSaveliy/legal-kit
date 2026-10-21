# Jurisdiction pack: Russian Federation (`ru`)

## Contents

- [Identity](#identity)
- [Scope](#scope)
- [Required files](#required-files)
- [Documents without templates](#documents-without-templates)
- [Templates](#templates)
- [Labels](#labels)
- [Pack rules](#pack-rules)

## Identity

| Field | Value |
|---|---|
| Code | `ru` |
| Requirement id prefix | `ru:` (ids are `ru:<slug>`, for example `ru:uvedomlenie-rkn-ob-obrabotke-pdn`) |
| Country | Russian Federation |
| Knowledge language | Russian (cards, templates, questions, document specs) |
| Descriptor language | English (this file) |
| Dialog and report | the user's language; legal documents are drafted in Russian |
| Snapshot | date and coverage are stated in `BASE.md` |

The pack follows the contract in [../README.md](../README.md).

## Scope

Requirements for websites, web apps and mobile apps (iOS, Android) owned by a Russian legal entity, an individual entrepreneur, a self-employed person (НПД) or a foreign owner serving users in Russia. Requirement records are grouped into directions:

| Direction | Topic |
|---|---|
| A | Owner status and jurisdiction |
| B | Personal data |
| C | Cookies, analytics, SDKs |
| D | Registration and authentication |
| E | User content and platforms |
| F | Commerce, payments, subscriptions |
| G | Advertising, mailings, push |
| H | Consumer information and language |
| I | Children and special audiences |
| J | Information security |
| K | Sector rules (finance, medicine, education, gambling, travel and others) |
| L | App stores and preinstallation |
| M | Rights to content and software |
| N | New technologies (AI and experimental regimes) |

Each requirement record carries the owner statuses it applies to (`ul`, `ip`, `npd`, `foreign`), business models (`b2b`, `b2c`), product kinds (`site`, `webapp`, `ios`, `android`), obligation (`general`, `conditional`, `sectoral`) and norm dates. Applicability is decided per record, never per direction.

## Required files

| Path | Kind | Produced by | Notes |
|---|---|---|---|
| `JURISDICTION.md` | hand-written | this pack | This descriptor. |
| `BASE.md` | generated | knowledge generator | Snapshot date and coverage. |
| `requirements.jsonl` | generated | knowledge generator | One record per requirement, id `ru:<slug>`. |
| `cards/` | generated | knowledge generator | `cards/<slug>.md`, full text with official URLs. |
| `templates/` | generated | template generator | `templates/<t>/text.md` and `templates/<t>/meta.md`. |
| `elements.json` | generated | template generator | Template elements with status and method. |
| `placeholders.json` | generated | template generator | Placeholder hints. |
| `forbidden-clauses.json` | generated | template generator | Clauses that must not appear. |
| `feature-map.json` | hand-written | feature map | Features and owner facts to requirement ids. |
| `owner-questions.md` | hand-written | this pack | [owner-questions.md](owner-questions.md) |
| `registries.md` | hand-written | this pack | [registries.md](registries.md) |
| `documents/` | hand-written | this pack | Specs listed below. |

## Documents without templates

The skill writes drafts of these documents to `.legal/drafts/<doc>.md` in the user's project. Each spec gives the purpose, basis ids, required elements with labels, what to look up at runtime, the draft path and who signs or files the document.

| Spec | Document |
|---|---|
| `documents/rkn-notification.md` | Notification to Roskomnadzor of intent to process personal data, and its changes |
| `documents/cross-border-notification.md` | Notification to Roskomnadzor of cross-border transfer of personal data |
| `documents/poruchenie.md` | Data-processing assignment (clauses for processors and vendors) |
| `documents/prikaz-otvetstvennyy.md` | Order appointing the person responsible for personal-data processing |
| `documents/lokalnye-akty.md` | Internal personal-data acts: per-purpose register, procedures, harm assessment, destruction records |
| `documents/incident-reglament.md` | Personal-data incident response procedure (24 h and 72 h notices) |
| `documents/subject-requests.md` | Procedure for data-subject requests and deletion |
| `documents/user-agreement.md` | User agreement, service rules, end-user licence |
| `documents/image-consent.md` | Consent to use a person's image |
| `documents/promo-rules.md` | Rules of a contest, prize draw or promotion |
| `documents/gift-cards.md` | Gift certificate terms |
| `documents/ord-erir-checklist.md` | Online advertising labelling checklist (ad label, erid, ERIR reporting) |
| `documents/kkt-checklist.md` | Cash-register receipts checklist (online cash register, OFD, self-employed receipts) |

## Templates

Templates cover the documents most products need; their specs live in `templates/<t>/meta.md`: `politika-obrabotki-pdn`, `soglasie-na-obrabotku-pdn`, `soglasie-na-rasprostranenie-pdn`, `soglasie-na-rassylku`, `cookie-banner-i-uvedomlenie`, `publichnaya-oferta-tovary`, `oferta-uslugi-i-podpiska`, `svedeniya-o-prodavce-i-vladelce-sayta`, `usloviya-vozvrata-i-obmena`. Document specs refer to templates by these names instead of repeating their text.

## Labels

Hand-written files of this pack label every element in Russian:

| Label | Meaning | May be "mandatory" |
|---|---|---|
| «норма» | stated by a law or regulation, cited with its article | yes, if the template element is mandatory and the source is the base or an official URL |
| «практика» | engineering or market practice | no |
| «трактовка» | interpretation of a norm, including court guidance | no |
| «вывод» | inference drawn by the knowledge base from the text of norms | no |
| «позиция органа» | regulator position, guidance page, FAQ or letter | no |
| «правило стора» | app store rule (Apple, Google Play, RuStore, AppGallery), not Russian law | no |

## Pack rules

- Facts that code cannot show are asked through [owner-questions.md](owner-questions.md): at most 5 first-run questions and one confirmation block of at most 10 questions after recon.
- Public registries are checked as described in [registries.md](registries.md). Status results are `ok`, `not_found`, `manual` or `error`; `manual` hands the lookup to the user with the URL, the key to enter and what to paste back.
- Russian is the authoritative language of drafted documents. An English version, when requested, is marked as a translation.
- When a document spec says the base has no norm (for example gift certificates or promotion rules), the skill researches at runtime under the research rules, labels the result with its source and never presents it as an obligation.
- Nothing in this pack is legal advice; the report says so.
