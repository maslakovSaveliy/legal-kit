---
id: order-confirmation-sent
title_ru: "Покупатель получает подтверждение заказа"
title_en: "The buyer gets an order confirmation"
reqs: [ru:publichnaya-oferta-i-podtverzhdenie-zakaza]
basis: norm
features: [commerce.checkout, commerce.cart_physical, commerce.digital_content, commerce.services_booking, commerce.subscription, payments.bot_invoice, payments.telegram_stars]
always: false
products: []
stacks: [nextjs, bot]
---

# The buyer gets an order confirmation

*Покупатель получает подтверждение заказа*

## Why

After the order the seller confirms the contract with its essential terms and the order number (`ru:publichnaya-oferta-i-podtverzhdenie-zakaza`).

## Incorrect

```ts
await db.order.create({ data }) // nothing sent
```

## Correct

```ts
const order = await db.order.create({ data })
await notify(order.contact, confirmation(order))
```

## In your stack

- [nextjs](../stacks/nextjs.md#legal-pages)
- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
