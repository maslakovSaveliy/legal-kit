# Bots and mini apps (Telegram, MAX)

Mechanics for editing an existing chat bot or a mini app inside a messenger. The bot's language stack (aiogram or python-telegram-bot in Python, grammY or Telegraf in TypeScript, the MAX clients) keeps its own guide for anything that is not chat-specific: a Python backend follows `python.md`, a Nest backend `nestjs.md`, a mini app is a web page and follows its web stack file for the page itself. The knowledge pack decides which flows need consent and which texts to show; this file shows the mechanics in a chat. Reuse the project's routers, keyboards, i18n and storage. Add no library.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in the chat](#consent-checkbox-in-the-chat) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and bot profile](#footer-and-bot-profile) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- Telegram: `aiogram`, `python-telegram-bot` (`telegram.ext`), `pyTelegramBotAPI` (`import telebot`), `telegraf`, `grammy`, `node-telegram-bot-api`; calls to `api.telegram.org/bot`.
- MAX: `@maxhub/max-bot-api`, `maxapi`, `max_client`; calls to `platform-api2.max.ru` (earlier `platform-api.max.ru`). The MAX documentation asks bot servers to trust the root certificate of the Russian Ministry of Digital Development: an HTTP client without it fails the TLS check.
- Mini app: `telegram-web-app.js`, `window.Telegram.WebApp`, `@telegram-apps/sdk`, `@twa-dev/sdk`; MAX Bridge exposes `window.WebApp`.
- Payments: `send_invoice` / `sendInvoice` with `provider_token` (a payment provider), currency `XTR` (Telegram Stars), `pre_checkout_query` handlers.
- Find the start handler (`/start`, `bot_started`), the menu and command list, the place where the bot asks for a phone number (`request_contact`, a contact button), and where user data is written (own database, `CloudStorage`, platform-side storage).

## Legal pages
- The documents live on web pages: the owner's site, or pages the run produces in `.legal/paste/html/` with a TODO to host them when there is no site. The existing route takes priority; never publish a duplicate policy page.
- In the bot, make them reachable without typing: a menu button or command (for example `/privacy` and `/terms`) that answers with links, the links in the bot description, and the policy link in the platform's bot settings when the platform has such a field.
- A mini app shows the same links in its own footer or settings screen, like any web page.

## Consent checkbox in the chat
- A chat has no checkbox, so consent is a separate action. The rule of a web form stays: unchecked by default means the user acts to give it; the consent action is separate from accepting the offer or terms.
- Two actions, two messages or two buttons: "accept the offer" and "consent to personal data processing", each next to the link to its text, sent before the user is asked for data. No button is pre-selected, and one button never accepts both.
- Ask for the phone number (contact button) only after the consent button was pressed. A refusal does not block what needs no consent (browsing a catalog, reading help).
- aiogram sketch:

```python
kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=t("consent.read"), url=POLICY_URL)],
    [InlineKeyboardButton(text=t("consent.agree"), callback_data="consent:grant")],
])
await message.answer(t("consent.text"), reply_markup=kb)

@router.callback_query(F.data == "consent:grant")
async def on_consent(call: CallbackQuery):
    await log_consent(call.from_user.id, action="grant")
    await call.message.answer(t("ask.phone"), reply_markup=phone_keyboard())
```

- grammY sketch: the same two inline buttons; the handler `bot.callbackQuery("consent:grant", ...)` logs the grant and only then sends the contact keyboard.
- Payments through a provider: request the contact needed for the receipt before the invoice (`need_email` or `need_phone_number`, and `send_email_to_provider` or `send_phone_number_to_provider` when the provider builds the receipt). Stars invoices ignore these fields: ask for the contact in the chat first if the product needs a receipt.

## Analytics gated by consent
- A chat bot has no cookies; events sent to an analytics service from the bot server are still processing of user data. Send them only for users whose analytics consent is logged, through one helper the handlers call.
- A mini app is a web page: gate its counters exactly as the web stack file does (no counter script before consent).

## Consent banner
- Chat bot: does not apply; the consent action above replaces it.
- Mini app: the web banner inside the webview, built from the mini app's own components: equal Accept and Reject, separate analytics and marketing toggles off by default, a settings entry to reopen it. Bump the consent version when the text changes so the banner returns for users whose stored version no longer matches.

## Consent log (existing backend only)
- Only if the bot already has a database and an ORM. NEVER introduce a new database or a BaaS for the log; platform storage (`CloudStorage`) is not a log.
- Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `channel` is `telegram` or `max`, `formId` names the flow (for example `start` or `checkout`), `subjectId` is the bot's internal user id, not the phone number.
- Log only `grant` and `revoke` (revoke = the user withdrew a consent, for example through a settings command); a first-time refusal is not logged: no consent was given, so there is nothing to prove.
- The log holds personal data (`subjectId` and the messenger user id it maps to): list it in the privacy policy, restrict read access, apply the retention period given by the documents step, and never store form contents or message texts in it.
- No database: report the gap with the field list (subject id, created time in UTC, consent version, text hash, channel, form id, action).

## Footer and bot profile
- The bot has no footer: put the owner's short name and a link to the requisites page in the bot description and in the answer to the help command.
- A mini app keeps the short web footer of its web stack.

## i18n
- Texts of buttons and consent messages live in the bot's translation catalog (aiogram i18n, grammY `@grammyjs/i18n`, the project's own dictionary); no hard-coded strings in handlers when the project already translates.

## Verify and record state
- Run the project's tests and linters without installing anything. Read the start, consent and checkout handlers: data is asked only after the consent action, the invoice asks for the receipt contact, the two actions are separate.
- Record every file the skill created or edited in `.legal/state.json` like any other stack. Commit nothing.
