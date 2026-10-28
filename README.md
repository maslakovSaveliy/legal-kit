# legal-kit

Agent Skill для юридического оформления сайта или приложения. / An Agent Skill that sets up the legal side of a website or an app.

Версия / version 0.1.0. [Русский](#русский) · [English](#english)

## Русский

legal-kit за один запуск разбирается, что делает продукт, подбирает применимые требования, пишет юридические документы и интерфейс согласий в стиле проекта и выдаёт отчёт о том, что осталось. Сейчас покрыто право Российской Федерации; другие юрисдикции пока не поддерживаются, структура рассчитана на добавление новых ([пакеты юрисдикций](skills/legal-kit/references/jurisdictions/README.md)).

### Что делает за один запуск

1. **Разведка (только чтение).** Код репозитория: стек, функции с файлом и строкой. Живой сайт: DOM, cookie и сетевые запросы до согласия, скриншоты для дизайна. Страницы приложения в сторах. Публичные реестры: ЕГРЮЛ и ЕГРИП, НПД, WHOIS, Банк России; реестр операторов ПДн РКН проверяется через браузер или пользователем.
2. **Применимые требования.** Из функций и фактов о владельце скилл выбирает требования из базы знаний. Отраслевые требования применяются только при отраслевом признаке и подтверждении владельца, будущие нормы уходят в «Дорожную карту» с датой.
3. **Один блок подтверждения.** Всё, чего скилл не видит (статус владельца, B2C или B2B, реквизиты, факты для документов), спрашивается одним сообщением, с догадкой скилла и её источником. Ждёт скилл только блокирующих пунктов.
4. **Документы и интерфейс согласий.** Политика обработки ПДн, согласия, cookie-баннер, оферта, условия возврата, сведения о продавце и другие документы (9 шаблонов и 13 описаний документов без шаблона). Страницы, отдельный чекбокс согласия, баннер, блок в футере и журнал согласий делаются в дизайне и каталогах i18n проекта; журнал согласий только при готовых бэкенде и ORM.
5. **Отчёт.** `.legal/report-YYYY-MM-DD.md` с разделами «Сделано», «Сделать вам», «Спорно» и «Дорожная карта».

### Три режима

- **Аудит и оформление** — продукт уже есть: всё, что описано выше.
- **План** — продукта ещё нет или кода почти нет («создаю сайт», «новый проект», «до разработки»). Функции берутся со слов владельца, скилл пишет `.legal/plan.md` — чек-лист для разработки с id требований — и `.legal/RULES.md`, короткие правила для агента, который пишет код. Готовит черновики документов, но в код ничего не встраивает. С вашего согласия добавляет в `CLAUDE.md`, `AGENTS.md` или `.cursor/rules` одну строку со ссылкой на `RULES.md`.
- **Фича** — в проект прямо сейчас добавляют одну функцию («добавляю оплату ЮKassa», «пишу Telegram-бота»): скилл отдаёт правила для неё из библиотеки `references/rules/`, без полного отчёта.

Боты и мини-приложения в Telegram и MAX — отдельный тип продукта (`bot`). Повторный аудит сравнивает план с кодом («План и факт»), а в конце каждого прогона скилл предлагает, что ещё можно улучшить, или пишет «Критичного нет».

### Чего не делает

- Это не юридическая консультация. Документы и решения стоит проверить с юристом.
- Не подаёт уведомления в РКН и ничего не регистрирует за вас: готовит текст и список шагов.
- Не подписывает и не отправляет документы.
- Не обходит капчу, гео-блок и вход через Госуслуги, не просит паспортные данные и логины Госуслуг: такую проверку передаёт вам.
- Не вводит данные и не отправляет формы на живом сайте и в сторах; в баннере согласия допускает только «Отклонить».
- Никогда не коммитит и не пушит. Правит проект только на чистом дереве или с вашего согласия, зависимости не ставит.
- Не выдумывает реквизиты и факты: они берутся из `.legal/answers.json`, запроса, самого продукта или реестра, остальное остаётся пунктом в «Сделать вам».
- Покрывает только право РФ. Для другой юрисдикции скилл скажет, что она не поддерживается, и не будет писать документы.

### Установка

```
npx skills add maslakovSaveliy/legal-kit
```

Для Claude Code:

```
/plugin marketplace add maslakovSaveliy/legal-kit
/plugin install legal-kit@legal-kit
```

В корне репозитория нет `SKILL.md`: скилл лежит в `skills/legal-kit/`.

### Требования

- **python3** (3.9+) желателен. Скрипты используют только стандартную библиотеку, ничего ставить не нужно. Без python3 в каждом файле workflow есть раздел «Without python3» с ручным вариантом.
- **Браузерный инструмент** (встроенный браузер, Claude in Chrome или Playwright MCP) желателен для проверки живого сайта. Без него скилл делает статический обход `scan_url.py`: JS не выполняется, и отчёт это отмечает.

### Примеры запуска

Репозиторий и рабочий сайт:

> Сделай юридическое оформление моего сайта по российскому законодательству. Код в текущей папке, сайт работает на https://example.ru. Правки вноси сам, но ничего не коммить.

Только адрес:

> Проверь сайт https://example.ru: что с ним не так по российскому закону? Кода у меня нет, только адрес. Ничего не правь.

Мобильное приложение:

> Приложение на Flutter лежит в текущей папке, страница в App Store: [ссылка]. Нужно юридическое оформление для российских пользователей: пользовательское соглашение, политика, согласие на push.

План до разработки:

> Делаю сайт магазина на Next.js: форма заявки, Яндекс Метрика, оплата ЮKassa, подписка. Кода пока нет — что учесть по закону?

Одна функция:

> Добавляю оплату через ЮKassa в Telegram-бота магазина — что сделать с чеком и согласиями?

### Что появится в проекте

Всё, что скилл хранит, лежит в `.legal/`:

| Путь | Содержимое |
|---|---|
| `.legal/answers.json` | факты о владельце, скрытые реквизиты, факты для документов и решения; повторный запуск читает его вместо повторных вопросов |
| `.legal/report-YYYY-MM-DD.md` | отчёт (машинный вид: `.legal/report.json`) |
| `.legal/drafts/` | черновики документов для владельца; в них могут остаться плейсхолдеры, в публичные страницы они не попадают |
| `.legal/plan.md` | режим «план»: чек-лист для разработки с id требований |
| `.legal/RULES.md` | правила для агента, который пишет код (не больше 60 строк) |
| `.legal/paste/<platform>/` | готовые к вставке материалы, если репозитория нет, сайт на конструкторе или у приложения нет сайта для документов |
| `.legal/.gitignore` | создаётся при первой записи; скрывает `answers.json` и `evidence/` |

Кроме того, `.legal/state.json` (файлы, которые создал или изменил скилл), `.legal/sources.json` (источники, найденные во время запуска) и `.legal/evidence/` (вывод сканеров и скриншоты). Правки в коде проекта остаются в рабочем дереве без коммита.

### База знаний

Требования, шаблоны и справочники лежат в `skills/legal-kit/references/jurisdictions/ru/`: 227 требований с карточками, 9 шаблонов документов, 322 элемента шаблонов со статусом и видом метода. Библиотека правил для разработки — `skills/legal-kit/references/rules/`: 32 правила, у каждого id требований из базы. **Дата базы: 2026-10-23** (`BASE.md`; отчёт печатает её одной строкой). Источники — официальные тексты (pravo.gov.ru и другие официальные сайты), для правил сторов — документация самих площадок. База — снимок на эту дату. Нормы, сроки и суммы берутся только из неё или из официального текста со ссылкой. «Обязательно» ставится только для нормы с источником в базе или по официальному адресу; трактовки, практика и правила сторов подаются как рекомендации или спорные места.

Пересборка сгенерированных файлов (требования, карточки, шаблоны, элементы, плейсхолдеры, запрещённые формулировки):

```
python3 tools/build_knowledge.py --wiki <путь к вашей копии исходной базы> --build-refs <путь к build_refs.py исходной базы> --out skills/legal-kit/references/jurisdictions/ru
```

`--build-refs` обязателен вместе с `--wiki`: это модуль исходной базы с картой направлений и короткими триггерами; он только читается и не копируется. Исходная база не входит в этот репозиторий. Сборка детерминирована, использует только стандартную библиотеку; `--check` сравнивает свежую сборку с `--out` и завершается кодом 1 при различиях. Рукописные файлы пакета (`feature-map.json`, `owner-questions.md`, `registries.md`, `documents/`) правятся напрямую.

### Оценка качества

В `evals/evals.json` 11 сценариев (лендинг, магазин на Next.js, SaaS на NestJS и React, приложения на Expo, Flutter и Swift, школа на Django, проверка только по адресу) с фикстурами в `evals/fixtures/` и офлайн-ответами реестров в `evals/stubs/`. `evals/triggers.json` — 20 запросов для проверки описания скилла (10 должны его запускать, 10 нет).

Итерация 1 (прогоны Sonnet, оценка ожиданий сценариев тоже Sonnet): со скиллом выполнено 75 из 98 ожиданий (77%) в 8 сценариях; без скилла 7 из 28 (25%) в 2 сценариях; со скиллом в тех же двух сценариях 21 из 28 (75%). Выборка маленькая, оценку ставила модель, после итерации 1 скилл дорабатывался, журналы прогонов в репозиторий не входят. Детерминированная проверка `check_run.py` нашла нарушения в 7 из 8 прогонов со скиллом той итерации.

Итерация 2 (прогон Sonnet с доработанным скиллом на двух сценариях: лендинг и магазин на Next.js; оценка тоже Sonnet): выполнено 24 из 28 ожиданий (86%) против 21 из 28 (75%) на тех же сценариях в итерации 1. Ожидания о подвале и реквизитах после этого приведены в соответствие с шаблоном базы, а доработки после итерации 2 в оценке заново не прогонялись; выборка по-прежнему маленькая.

Как проверить прогон: скопируйте фикстуру в чистую папку (`git init`, коммит-основа), запустите промпт сценария с `LEGAL_KIT_OFFLINE=1 LEGAL_KIT_STUBS=<репозиторий>/evals/stubs`, затем:

```
python3 evals/check_run.py <папка проекта, с которым работал скилл>
```

`check_run.py` запускает `report.py verify` по `.legal/report.json` и `check_docs.py` по черновикам и изменённым страницам; код выхода 0 — проверки пройдены, 1 — найдены нарушения, 2 — проверку не удалось выполнить. Для сценариев «только адрес» фикстуру можно поднять локально: `evals/serve.sh <фикстура> [порт]` (порт по умолчанию 8731, `.legal/` в раздачу не попадает).

### Разработка

```
python -m pytest tools/tests -q
```

Нужен pytest (только для разработки). Тесты проверяют упаковку скилла, ссылки, сгенерированные данные, скрипты и схему evals; тест утечек просматривает все текстовые файлы репозитория, включая этот файл, кроме папки `tools/` (генератор и его тесты) и рабочих папок (`.git`, `.venv`, `.superpowers`, кэши, `evals/workspace`). Скилл лежит в `skills/legal-kit/`, генератор и тесты в `tools/`, сценарии оценки в `evals/`.

### Лицензия

[MIT](LICENSE) с пунктом «Сгенерированные документы»: документы и тексты, которые скилл создаёт из своих шаблонов для вашего продукта (политики, оферты, тексты согласий, уведомления и подобные), можно размещать, изменять и использовать без указания авторства и без включения текста лицензии. Изменения: [CHANGELOG.md](CHANGELOG.md).

## English

legal-kit sets up the legal side of a product in one run: it finds out what the product does, selects the requirements that apply, writes the legal documents and the consent UI in the project's own design, and reports what is left. Today it covers the law of the Russian Federation; other jurisdictions are not supported yet, and the structure is built to add them ([jurisdiction packs](skills/legal-kit/references/jurisdictions/README.md)).

### What one run does

1. **Recon (read-only).** The repository: stacks, features with file and line. The live site: DOM, cookies and network requests before consent, screenshots for the design. App store listings. Public registries: the company and sole-trader registers (EGRUL/EGRIP), the self-employed status (NPD), WHOIS, the Bank of Russia; the Roskomnadzor register of personal-data operators is checked through a browser or by the user.
2. **Applicable requirements.** From the features and the owner's facts the skill selects requirements from the knowledge base. Sector rules apply only with a sector sign and the owner's confirmation; future norms go to the roadmap with their date.
3. **One confirmation block.** Whatever the skill cannot see (owner status, B2C or B2B, requisites, facts for the documents) is asked in a single message, each item with the skill's guess and its source. The run waits only for blocking items.
4. **Documents and consent UI.** Privacy policy, consents, cookie banner, public offer, refund terms, seller details and other documents (9 templates and 13 specs of documents without a template). Pages, a separate consent checkbox, a banner, a footer block and a consent log follow the project's design and i18n catalogs; the consent log only on an existing backend and ORM.
5. **Report.** `.legal/report-YYYY-MM-DD.md` with the sections «Сделано» (done), «Сделать вам» (to do on your side), «Спорно» (disputed) and «Дорожная карта» (roadmap).

### Three modes

- **Audit and setup**: the product exists; everything described above.
- **Plan**: the product is not built yet or the code is nearly empty ("new project", "build checklist", «создаю сайт»). Features come from the owner's words; the skill writes `.legal/plan.md`, a development checklist with requirement ids, and `.legal/RULES.md`, short rules for the agent that writes the code. It drafts documents but integrates nothing. With your OK it adds one line linking `RULES.md` to `CLAUDE.md`, `AGENTS.md` or `.cursor/rules`.
- **Feature**: one function is being added now ("adding YooKassa payments", "writing a Telegram bot"): the skill gives the rules for it from the `references/rules/` library, without a full report.

Bots and mini apps in Telegram and MAX are a product kind of their own (`bot`). A rerun audit compares the plan with the code ("plan vs fact"), and every run ends with what can be improved, or says "nothing critical".

### What it does not do

- It is not legal advice. Have the documents and decisions checked by a lawyer.
- It does not file notifications with Roskomnadzor or register anything for you: it prepares the text and the list of steps.
- It does not sign or send documents.
- It does not bypass a captcha, a geo-block or the Gosuslugi login, and never asks for passport data or Gosuslugi credentials: such a lookup is handed to you.
- It enters no data and submits no forms on the live site or in stores; on a consent banner it only allows "Reject".
- It never commits or pushes. It edits the project only on a clean tree or with your OK, and installs no dependencies.
- It does not invent requisites or facts: they come from `.legal/answers.json`, the prompt, the product itself or a registry; the rest becomes an item in «Сделать вам».
- It covers Russian law only. For another jurisdiction it says so plainly and drafts nothing.

### Install

```
npx skills add maslakovSaveliy/legal-kit
```

For Claude Code:

```
/plugin marketplace add maslakovSaveliy/legal-kit
/plugin install legal-kit@legal-kit
```

The repository root has no `SKILL.md`: the skill lives in `skills/legal-kit/`.

### Requirements

- **python3** (3.9+) is recommended. The scripts use the standard library only; nothing needs installing. Without python3, every workflow file has a "Without python3" section with the manual equivalent.
- **A browser tool** (the built-in browser, Claude in Chrome or Playwright MCP) is recommended for checking the live site. Without one the skill falls back to the static crawl `scan_url.py`: JavaScript is not executed, and the report says so.

### Example prompts

Repo and live site:

> Set up the legal side of this site for Russian users. The code is in the current folder, the site is live at https://example.com. Apply the fixes yourself, but don't commit anything.

URL only:

> Check https://example.com against Russian law: what is wrong with it? I have no code, only the address. Don't change anything.

Mobile app:

> This is our Flutter app (code in the current folder, App Store page: [link]). Do the legal setup for Russian users: terms of use, privacy policy, consent for push notifications.

### What lands in your project

Everything the skill keeps lives in `.legal/`:

| Path | Content |
|---|---|
| `.legal/answers.json` | owner facts, withheld requisites, document facts and decisions; a rerun reads it instead of asking again |
| `.legal/report-YYYY-MM-DD.md` | the report (machine form: `.legal/report.json`) |
| `.legal/drafts/` | document drafts for the owner; they may keep placeholders, public pages may not |
| `.legal/plan.md` | plan mode: the development checklist with requirement ids |
| `.legal/RULES.md` | rules for the agent that writes the code (at most 60 lines) |
| `.legal/paste/<platform>/` | paste-ready artifacts when there is no repo, the site runs on a no-code platform, or the app has no website for its documents |
| `.legal/.gitignore` | created on the first write; hides `answers.json` and `evidence/` |

Also `.legal/state.json` (the files the skill created or edited), `.legal/sources.json` (sources found during the run) and `.legal/evidence/` (scanner output and screenshots). Edits to the project's code stay in the working tree, uncommitted.

### Knowledge base

Requirements, templates and reference files live in `skills/legal-kit/references/jurisdictions/ru/`: 227 requirements with cards, 9 document templates, 322 template elements with a status and a method kind; the rules library for development is `skills/legal-kit/references/rules/` (32 rules, each with requirement ids from the base). **Base date: 2026-10-23** (`BASE.md`; the report prints it in one line). Sources are official texts (pravo.gov.ru and other official sites) and, for store rules, the platforms' own documentation. The base is a snapshot of that date. Norms, deadlines and amounts come only from it or from an official text with its URL. "Mandatory" is set only for a norm whose source is the base or an official URL; interpretations, practice and store rules are presented as recommendations or disputed points.

To regenerate the generated files (requirements, cards, templates, elements, placeholders, forbidden clauses):

```
python3 tools/build_knowledge.py --wiki <path to your copy of the source base> --build-refs <path to the source base's build_refs.py> --out skills/legal-kit/references/jurisdictions/ru
```

`--build-refs` is required together with `--wiki`: it is the source base's module with the directory map and the short triggers, read and never copied. The source base is not part of this repository. The build is deterministic and uses only the standard library; `--check` compares a fresh build with `--out` and exits 1 on any difference. The pack's hand-written files (`feature-map.json`, `owner-questions.md`, `registries.md`, `documents/`) are edited directly.

### Evaluation

`evals/evals.json` holds 11 scenarios (a landing page, a Next.js shop, a NestJS and React SaaS, Expo, Flutter and Swift apps, a Django school, a URL-only audit) with fixtures in `evals/fixtures/` and offline registry answers in `evals/stubs/`. `evals/triggers.json` has 20 queries that test the skill's description (10 should trigger it, 10 should not).

Iteration 1 (Sonnet runs, expectations also graded by Sonnet): with the skill 75 of 98 expectations passed (77%) across 8 scenarios; without it 7 of 28 (25%) across 2 scenarios; with the skill on those same two scenarios 21 of 28 (75%). The sample is small, a model did the grading, the skill was revised after iteration 1, and the run logs are not part of the repository. The deterministic `check_run.py` found violations in 7 of the 8 with-skill runs of that iteration.

Iteration 2 (Sonnet runs with the revised skill on two scenarios, the landing page and the Next.js shop; graded by Sonnet too): 24 of 28 expectations passed (86%), against 21 of 28 (75%) on the same two scenarios in iteration 1. The expectations about the footer and the requisites were afterwards aligned with the knowledge base's template, and the fixes made after iteration 2 were not run through the evaluation again; the sample is still small.

To check a run: copy a fixture into a clean folder (`git init` and a baseline commit), run the scenario's prompt with `LEGAL_KIT_OFFLINE=1 LEGAL_KIT_STUBS=<repo>/evals/stubs`, then:

```
python3 evals/check_run.py <the project folder the skill worked on>
```

`check_run.py` runs `report.py verify` on `.legal/report.json` and `check_docs.py` on the drafts and the changed pages; exit code 0 means both checks pass, 1 means violations, 2 means the check could not run. For the URL-only scenarios a fixture can be served locally: `evals/serve.sh <fixture> [port]` (default port 8731; `.legal/` is left out of what is served).

### Development

```
python -m pytest tools/tests -q
```

pytest is needed for development only. The tests cover skill packaging, links, the generated data, the scripts and the evals schema; the leak scan reads every text file in the repository, this file included, except the `tools/` folder (the generator and its tests) and working folders (`.git`, `.venv`, `.superpowers`, caches, `evals/workspace`). The skill is in `skills/legal-kit/`, the generator and tests in `tools/`, the evaluation scenarios in `evals/`.

### License

[MIT](LICENSE) with a "Generated documents" clause: documents and texts that the skill generates from its templates for your product (policies, offers, consent texts, notices and similar) may be published, modified and used without attribution and without including the license text. Changes: [CHANGELOG.md](CHANGELOG.md).
