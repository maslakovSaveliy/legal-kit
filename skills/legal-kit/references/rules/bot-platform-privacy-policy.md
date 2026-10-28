---
id: bot-platform-privacy-policy
title_ru: "Своя политика конфиденциальности указана в настройках бота"
title_en: "The bot's own privacy policy is set on the platform"
reqs: [ru:pravila-platform-botov-dannye-i-dopusk]
basis: platform
features: [bot.telegram, bot.max, bot.mini_app]
always: false
products: [bot]
stacks: [bot]
---

# The bot's own privacy policy is set on the platform

*Своя политика конфиденциальности указана в настройках бота*

## Why

Telegram and MAX ask bot developers to publish a privacy policy; this is a platform rule, not Russian law (`ru:pravila-platform-botov-dannye-i-dopusk`).

## Incorrect

```text
Bot settings: privacy policy — empty (platform default)
```

## Correct

```text
Bot settings: privacy policy — https://shop.example.ru/legal/privacy
```

## In your stack

- [bot](../stacks/bot.md#legal-pages)
