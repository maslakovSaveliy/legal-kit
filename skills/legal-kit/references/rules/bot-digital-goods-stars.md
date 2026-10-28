---
id: bot-digital-goods-stars
title_ru: "Цифровые товары в Telegram-боте — через Stars"
title_en: "Digital goods in a Telegram bot are sold for Stars"
reqs: [ru:pravila-platform-botov-oplata]
basis: platform
features: [payments.telegram_stars, payments.bot_invoice]
always: false
products: [bot]
stacks: [bot]
---

# Digital goods in a Telegram bot are sold for Stars

*Цифровые товары в Telegram-боте — через Stars*

## Why

Telegram's rules route digital goods in bots through Stars and require payment support commands; this is a platform rule, and the receipt question for Stars stays open in the knowledge pack (`ru:pravila-platform-botov-oplata`).

## Incorrect

```py
await bot.send_invoice(chat_id, 'E-book', '', 'book', provider_token=TOKEN, currency='RUB', prices=prices)
```

## Correct

```py
await bot.send_invoice(chat_id, 'E-book', '', 'book', provider_token='', currency='XTR', prices=prices)
# plus /paysupport and /terms handlers
```

## In your stack

- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
