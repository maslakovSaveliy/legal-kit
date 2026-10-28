---
id: receipt-contact-before-payment
title_ru: "Контакт для чека — до оплаты"
title_en: "The receipt contact is collected before payment"
reqs: [ru:onlayn-kkt-i-elektronnyy-chek]
basis: norm
features: [payments.yookassa, payments.cloudpayments, payments.tbank, payments.robokassa, payments.sbp, payments.bnpl, payments.bot_invoice, payments.telegram_stars, payments.receipts_kkt, commerce.checkout]
always: false
products: []
stacks: [nextjs, bot]
---

# The receipt contact is collected before payment

*Контакт для чека — до оплаты*

## Why

For an online payment the electronic receipt goes to the phone or e-mail the buyer gave before paying (`ru:onlayn-kkt-i-elektronnyy-chek`). A checkout that does not ask for it cannot send the receipt.

## Incorrect

```py
await message.answer_invoice(title, description, payload, provider_token=TOKEN, currency='RUB', prices=prices)
```

## Correct

```py
await message.answer_invoice(title, description, payload, provider_token=TOKEN, currency='RUB',
                             prices=prices, need_email=True, send_email_to_provider=True)
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
