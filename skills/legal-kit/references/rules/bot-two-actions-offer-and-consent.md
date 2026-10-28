---
id: bot-two-actions-offer-and-consent
title_ru: "В боте — два действия: оферта и согласие"
title_en: "In a bot, the offer and the consent are two actions"
reqs: [ru:dokumenty-i-soglasiya-v-chat-bote]
basis: interpretation
features: [bot.telegram, bot.max, bot.mini_app]
always: false
products: [bot]
stacks: [bot]
---

# In a bot, the offer and the consent are two actions

*В боте — два действия: оферта и согласие*

## Why

A chat has no checkbox; carrying the separate-consent rule into a bot as two separate buttons is a reading of the rules for forms (`ru:dokumenty-i-soglasiya-v-chat-bote`).

## Incorrect

```py
InlineKeyboardButton(text="Принимаю всё", callback_data="ok")
```

## Correct

```py
InlineKeyboardButton(text="Принимаю оферту", callback_data="offer:accept")
InlineKeyboardButton(text="Согласен на обработку ПДн", callback_data="consent:grant")
```

## In your stack

- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
