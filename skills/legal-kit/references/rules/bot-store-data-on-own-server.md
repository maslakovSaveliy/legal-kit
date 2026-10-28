---
id: bot-store-data-on-own-server
title_ru: "Данные бота — на своём сервере в РФ, не в хранилище платформы"
title_en: "Bot data lives on the owner's server in Russia, not in platform storage"
reqs: [ru:pdn-pri-sbore-cherez-inostrannyy-messendzher]
basis: interpretation
features: [bot.telegram, bot.max, bot.mini_app]
always: false
products: [bot]
stacks: [bot]
---

# Bot data lives on the owner's server in Russia, not in platform storage

*Данные бота — на своём сервере в РФ, не в хранилище платформы*

## Why

Whether storage on a foreign messenger's side is the owner's database is open; keeping customer data in the bot's own database in Russia avoids the question (`ru:pdn-pri-sbore-cherez-inostrannyy-messendzher`).

## Incorrect

```js
Telegram.WebApp.CloudStorage.setItem('phone', phone)
```

## Correct

```js
await fetch('/api/customers', { method: 'POST', body: JSON.stringify({ phone }) })
```

## In your stack

- [bot](../stacks/bot.md#consent-log-existing-backend-only)
