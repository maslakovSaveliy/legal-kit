# Documents (phase 5)

## Contents

- [Which documents](#which-documents)
- [Drafting from a template](#drafting-from-a-template)
  - [Blocks and conditions](#blocks-and-conditions)
  - [Placeholders](#placeholders)
  - [Drafts and public pages](#drafts-and-public-pages)
  - [Disputed places](#disputed-places)
- [Documents without a template](#documents-without-a-template)
- [Existing legal pages](#existing-legal-pages)
- [Language](#language)
- [Check the drafts](#check-the-drafts)
- [Without python3](#without-python3)

Templates and their data are in `references/jurisdictions/ru/templates/` (index: [templates/README.md](../jurisdictions/ru/templates/README.md)). The pack's rules on labels and obligation levels are in [JURISDICTION.md](../jurisdictions/ru/JURISDICTION.md#labels).

This phase never waits for the user. A fact still unknown after the confirmation block keeps the conservative variant or a placeholder in the draft, and the question goes to the report («Сделать вам»); a public page is built only from a draft without unresolved placeholders, except a passage the template keeps only once a fact is confirmed, which the page leaves out ([Drafts and public pages](#drafts-and-public-pages)).

## Which documents

1. Start from `templates` (with `template_reasons`) and `documents` in the `select.py` output ([applicability.md](applicability.md#run-selectpy)); the feature map's trigger sections chose them from features and owner facts.
2. Confirm each one a second time: for a template read section 1 of its `meta.md` («Назначение и когда нужен»): when it is needed, who does not need it, what it does not cover. Draft it only if the product meets that trigger too. A site that sells nothing gets no offer and no returns page; a site that collects no personal data (no forms, accounts, counters or SDKs) gets no policy and no consent text, and the policy row says it becomes necessary once data is collected.
3. Offers: physical goods use `publichnaya-oferta-tovary`; services, subscriptions, courses, bookings and digital access use `oferta-uslugi-i-podpiska`; a product with both gets both.
4. One draft per template for the whole product, whatever number of features triggered it: one policy, one personal-data consent text, one banner text.
5. The user's explicit request («нужна оферта») does not override the trigger: if the template's section 1 says it is not needed, say so and explain.

## Drafting from a template

Read `meta.md` sections 1, 5 and 6 and the text in `text.md` section 3. Element codes such as «А4» in the templates' prose are template elements in `elements.json` (`template`, `id`, `status`, `method`, `requirements`).

A draft is assembled **only** from the fenced code blocks marked `markdown` in `text.md`, plus the `[если …]` branches chosen for the product. Prose and tables outside the fences are guidance and lint material and are never copied into a draft: for example subsection 3.2 «Чего не должно быть в тексте оферты» of `publichnaya-oferta-tovary` lists wordings that `check_docs.py` reports as forbidden clauses.

### Blocks and conditions

- Section 1 of `meta.md` may hold a fork table that picks blocks by situation. For consent (`soglasie-na-obrabotku-pdn`) the table decides per form and per purpose whether the basis is the contract (a notice with a policy link at the submit button, no checkbox) or consent (a separate checkbox and the consent text). Record the choice for each form; ui-integration builds exactly that, and the report names the basis.
- An explicit wish of the user for consent at a form («согласие у формы записи», "consent at sign-up", "a consent checkbox"), stored in `decisions.consent_at_forms`, overrides the contract branch for that form: build a separate unchecked consent checkbox with the consent text, even where the table allows a notice, and record in the report that the owner asked for it. A rerun reads the list and keeps those checkboxes. Without such a wish keep the table's choice (a notice with a policy link for the contract basis) and offer the consent checkbox as the alternative in a `disputed` row («Спорно»).
- Take only the blocks the table and the product need (subsections 3.x of `text.md`).
- Resolve every square bracket inside the fenced text from facts in `answers.json` and recon:
  - conditions `[если …]`, `[юридическое лицо:]` and other `[…:]` markers: keep the text without the marker when the condition holds, delete the whole bracket when it does not;
  - optional fragments such as `[, телефон {{ТЕЛЕФОН}}]`: keep the fragment when the fact exists, else delete it;
  - alternatives `[или: …]`, `[вариант: …]`: keep one variant;
  - notes to the author such as `[Оставьте только …]`: follow them and delete them;
  - button labels in UI mock-ups such as `[ Принять все ]` are not markers: they become the buttons built in phase 6.
- When a fact is unknown (not answered in the confirmation block), keep the conservative variant and list the choice in the report. No bracket marker stays in a draft.

### Placeholders

Before drafting, make `answers.json` hold every value the run knows: requisites from `ok` registry answers and the owner's replies in `owner`; document facts from recon, the owner's replies and accepted proposals in `document_facts` ([intake.md](intake.md#document-facts)). Drafts, pages and `check_docs.py` then use one source.

Each `{{ИМЯ}}` has a hint in `placeholders.json` and a row in section 5 of `meta.md`. `check_docs.py` sorts them into three kinds:

| Kind | Examples | Source | When unknown |
|---|---|---|---|
| Requisites (`placeholder_requisite`) | `{{НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА}}`, `{{ИНН}}`, `{{ОГРН_ИЛИ_ОГРНИП}}`, `{{АДРЕС}}`, `{{EMAIL_ДЛЯ_ОБРАЩЕНИЙ}}`, `{{ТЕЛЕФОН}}`, licence and registration data; `{{ОТВЕТСТВЕННЫЙ_ЗА_ОБРАБОТКУ_ПДН}}` and `{{КОНТАКТЫ_ОТВЕТСТВЕННОГО}}` from `owner.pd_officer` | `owner` in `answers.json`, the prompt, the product itself, an `ok` registry answer | never a likely value. Withheld by the owner (`owner.withheld`): stays visible as `{{…}}`, on public pages too, with a «Сделать вам» row. Otherwise it is a blocking item of the confirmation block; if it is still unknown, it stays in the draft only |
| Document facts (`placeholder_fact`) | data fields, purposes, recipients and their countries, counters and SDKs, database region, retention periods, support hours, delivery and return terms, URLs of the legal pages | recon evidence, `document_facts`, the routes ui-integration creates | asked in the confirmation block, with a proposal where it is a business choice; if it is still unknown, it stays in the draft only, with a «Сделать вам» row |
| Runtime values (`placeholder_runtime`) | per user, order or message: `{{ИМЯ_ПОКУПАТЕЛЯ}}`, `{{НОМЕР_ЗАКАЗА}}`, `{{ДАТА_СОГЛАСИЯ}}`, `{{ССЫЛКА_ОТПИСКИ}}`, `{{ФИО_ПОЛЬЗОВАТЕЛЯ}}` (the hint «Подставляются системой» and the confirmation, consent and mailing texts) | the product's own data at run time | never asked: before integration each becomes the project's interpolation bound to the real field (`{name}`, `${order.number}`, `{{ order.number }}` in a template engine); in a draft it stays as is |

A foreign owner (`owner.status` `foreign`) has its own variant only in the requisites template (variant Г of `svedeniya-o-prodavce-i-vladelce-sayta`, with `{{СТРАНА_РЕГИСТРАЦИИ}}` and `{{РЕГИСТРАЦИОННЫЙ_НОМЕР}}`). The other templates name the owner by Russian identifiers: «ИНН {{ИНН}}», «ОГРН {{ОГРН_ИЛИ_ОГРНИП}}» or «ОГРНИП {{ОГРН_ИЛИ_ОГРНИП}}», a bare `{{ОГРН_ИЛИ_ОГРНИП}}` (the offer's signature lines), an address «по ЕГРЮЛ». For a foreign owner, in every such place of a draft: the OGRN identifier becomes «страна регистрации {{СТРАНА_РЕГИСТРАЦИИ}}, регистрационный номер {{РЕГИСТРАЦИОННЫЙ_НОМЕР}}», «ИНН {{ИНН}}» stays only when the owner gives an INN, «по ЕГРЮЛ» is dropped, and the offer takes its `[юридическое лицо:]` fork. The values come from `owner.country` (the country named in Russian) and `owner.reg_number`; a withheld registration number is `РЕГИСТРАЦИОННЫЙ_НОМЕР` in `owner.withheld`. Only the identifiers change; the rest of the template text stays as it is. `check_docs.py` reports an OGRN label in a foreign owner's document as a mismatch and checks that the number after «регистрационный номер» is `owner.reg_number`.

Template defaults are not placeholders to ask about: the edition date is the run date; the version continues the existing document's numbering or starts at 1.0; a variant from section 6 follows [Disputed places](#disputed-places).

### Drafts and public pages

- Mode `plan` drafts the documents before any code exists: drafts only, no public page ([plan.md](plan.md#plan-mode)).
- `.legal/drafts/<doc>.md` are documents for the owner. They may keep placeholders only the owner can fill: signature, signing date, internal numbers, unknown facts and requisites. `check_docs.py` reports them with `"blocking": false`.
- A public page is any text the product shows its users: a legal page, the footer or owner block, banner and checkbox texts, catalog entries, a Documents screen, and the paste artifacts in `.legal/paste/`. It carries no `{{…}}` except the requisites listed in `owner.withheld`, which stay visible and go to «Сделать вам».
- A passage the template keeps only once a fact is confirmed (a bracketed note «Заполняйте, только если …», «Заполняйте только после …», «оставляйте, только если …» or «… только если это сделано», such as the storage region `{{РЕГИОН_РАЗМЕЩЕНИЯ_БД}}` in section 5 of the policy and in the cookie notice) is left out of the public page while that fact is unknown: the page is published without the passage, a heading left without text goes too, the draft keeps the passage with its placeholder, and «Сделать вам» names the fact and the passage to add on the next run. A placeholder outside such a passage still holds the page back.
- A requisite that fails its check digit stays in the draft as the owner gave it, the page that needs it stays a draft, and «Сделать вам» names the number to re-check. Never drop the number or change a digit to pass the check.
- `owner.withheld` lists only what the owner refused to give; the skill never adds a requisite to it. A requisite the owner does not know («не знаю») or an owner who is unavailable leaves the value unknown, and the pages that need it stay drafts. Texts that need no unknown value (a form notice, a banner text) are still integrated or pasted. While the new policy waits in the drafts, their policy link points to the policy page the site already has, and «Сделать вам» names the pages that wait, the values they wait for and the links to repoint once they are published; a site with no policy page at all keeps these texts waiting with the policy.
- A draft with any other unresolved requisite or document fact is not integrated: no page is created from it and an existing page is not rewritten with it. The draft stays in `.legal/drafts/`, and «Сделать вам» names the missing values and the page that waits for them; the next run integrates it once `answers.json` has them.
- Runtime values are not unknowns: a message, confirmation or consent text that reaches the product (an e-mail template, a confirmation screen) uses the project's own interpolation with the real field names, so no `{{ИМЯ}}` of the pack is left; a template engine's own `{{ order.number }}` with a Latin identifier is that interpolation, not a placeholder.
- Wording that hides an unknown value (an underscore blank, «уточняется», a likely value) is no fix: it is the same unresolved placeholder in other words.

### Disputed places

Section 6 of `meta.md` lists disputed points with variants; the decision belongs to the owner. Take the variant the template calls conservative (or protective), write it, and add a `disputed` row naming the point, the variant used and the alternative.

## Documents without a template

`documents` from `select.py` comes from the feature map's trigger section (a map without that section falls back to every spec that cites an applicable id, which is broader). For each entry read the spec `references/jurisdictions/ru/documents/<doc>.md` and draft it only when its «Назначение» (when needed) holds for this product: a landing that sells nothing gets no gift-certificate terms, a product without promotions no promotion rules. Then follow the spec: basis ids, the elements table with labels, the runtime lookups, the draft path and who signs or files it. Write the draft to `.legal/drafts/<doc>.md`.

- Only elements labelled «норма» are obligations; «практика», «трактовка», «вывод», «позиция органа» and «правило стора» are written as such.
- A spec that says the base has no norm (gift certificates, promotion rules) sends the topic to research ([research-rules.md](research-rules.md)); the result is labelled with its source and never presented as an obligation.
- Checklists (`kkt-checklist`, `ord-erir-checklist`) and notification data sheets (`rkn-notification`, `cross-border-notification`) are prepared for the owner to act on; the skill never files anything.

## Existing legal pages

Existing pages (from `legal_pages` of the repo scan, links found on the site) are edited in place, never duplicated:

1. Read the full text. For an offer, extract the text into `.legal/evidence/existing/<name>.txt` and run `check_docs.py --kind offer` on it to find forbidden clauses; map each hit back to the line of the source file.
2. Report each hit with that file and line as evidence. Severity `violation`: a row for the requirement the clause breaks (for example `ru:nedopustimye-usloviya-oferty`, or `ru:vozvrat-tovara-pri-distancionnoy-prodazhe` for a no-return clause). Severity `risk`: its own row with `level` and `basis` `interpretation`, bucket `disputed`; the clause is not called a violation and the owner decides whether to keep it.
3. Rewrite the page from the new draft at the same route and in the same component; keep its layout. Violating clauses are gone from the final text; risk clauses stay unless the owner removes them.
4. Show the user the diff of every existing legal page (`git diff -- <path>`), or the old and new text side by side without git.

## Language

- Russian is the authoritative text of every document drafted under the `ru` pack, whatever language the dialog uses.
- An English version is made only when the user asks or the product has an English locale. It goes to `.legal/drafts/<name>.en.md` and to the English page, and starts with a notice that it is a translation and the Russian text prevails; in an i18n project the notice is a catalog key (for example `Legal.translationNotice`).
- The translation keeps every requisite exactly as in `answers.json`: the owner's name in its registered Russian form (a transliteration may follow in brackets), INN, OGRN, address, e-mail and phone unchanged, so `check_docs.py` finds no mismatch.

## Check the drafts

```sh
python3 <skill>/scripts/check_docs.py .legal/drafts/*.md --public <page> --public <file> \
  --answers .legal/answers.json --kb <skill>/references/jurisdictions/ru
```

Drafts come first, before any option; every public file gets its own `--public` (the flag takes one file and is repeated). Public files are: the pages integrated in phase 6, the project files that show legal text (footer, layout, catalogs, consent texts) and the paste artifacts. Before phase 6 run it on the drafts alone. It prints `{files, public, issues, summary, blocking}`; each issue has `blocking`, and the script exits 1 only while a blocking issue is left:

| Kind | Blocks | Fix |
|---|---|---|
| `placeholder_requisite` | on a public page, unless the owner withheld it | fill it from a valid source; a withheld requisite stays visible, with a «Сделать вам» row |
| `placeholder_fact` | on a public page | fill it from `document_facts` or recon; otherwise keep the page in the drafts ([Drafts and public pages](#drafts-and-public-pages)) |
| `placeholder_runtime` | on a public page | convert it to the project's interpolation bound to the real field |
| `condition` | always | resolve the leftover `[если …]` marker |
| `inn_checksum`, `ogrn_checksum` | on a public page | the number is wrong where it came from: re-check the source, never adjust digits; the draft keeps it, the page that needs it stays a draft, and «Сделать вам» names the number |
| `mismatch` | always | the text differs from `answers.json`: use the confirmed value |
| `forbidden_clause` | severity `violation` | remove or rewrite it; severity `risk` is reported without blocking and goes to «Спорно» ([Existing legal pages](#existing-legal-pages)) |
| `encoding` | never | the file is not UTF-8 and was read as the named encoding (`cp1251` or `utf-16`): its text was still checked; convert the page to UTF-8 when the project allows it |

Repeat until it exits 0. The pages built from the drafts carry the same text, without the passages left out under [Drafts and public pages](#drafts-and-public-pages).

## Without python3

Check the drafts and pages by hand: search for `{{` and `[если`; on a public page every `{{…}}` with a Cyrillic name must be a requisite listed in `owner.withheld`, and per-user values use the project's interpolation; recompute the check digits (a 10-digit INN: the first 9 digits times 2, 4, 10, 3, 5, 9, 4, 6, 8, summed, mod 11 mod 10, equal the 10th digit; a 12-digit INN: the first 10 digits times 7, 2, 4, 10, 3, 5, 9, 4, 6, 8 give the 11th digit and the first 11 times 3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8 give the 12th, each sum mod 11 mod 10; a 13-digit OGRN: the number formed by the first 12 digits mod 11 mod 10 is the 13th digit; a 15-digit OGRNIP: the first 14 digits mod 13 mod 10 is the 15th), or list the numbers in «Сделать вам» for the owner to confirm against the registry; compare every requisite with `answers.json`; read each `pattern_text` of `<skill>/references/jurisdictions/ru/forbidden-clauses.json` for the offer's template and search the offer for those wordings with `grep -F`.
