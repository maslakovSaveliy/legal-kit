---
id: bot-receipt-contact-before-invoice
title_ru: "В боте — контакт для чека до счёта"
title_en: "A bot asks for the receipt contact before the invoice"
reqs: [ru:oplata-v-chat-bote-i-chek]
basis: interpretation
features: [payments.bot_invoice, payments.telegram_stars]
always: false
products: [bot]
stacks: [bot]
---

# A bot asks for the receipt contact before the invoice

*В боте — контакт для чека до счёта*

## Why

Applying the receipt rules to an in-chat payment is a reading of them; the safe way is to ask for e-mail or phone before the invoice (`ru:oplata-v-chat-bote-i-chek`).

## Incorrect

```py
await bot.send_invoice(chat_id, title, description, payload, provider_token=TOKEN, currency='RUB', prices=prices)
```

## Correct

```py
await bot.send_invoice(chat_id, title, description, payload, provider_token=TOKEN, currency='RUB',
                       prices=prices, need_phone_number=True, send_phone_number_to_provider=True)
```

## In your stack

- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
