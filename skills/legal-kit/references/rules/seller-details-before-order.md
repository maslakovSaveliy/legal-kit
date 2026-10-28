---
id: seller-details-before-order
title_ru: "Сведения о продавце — до оформления заказа"
title_en: "Seller details are shown before the order"
reqs: [ru:svedeniya-o-prodavce-pri-distancionnoy-prodazhe]
basis: norm
features: [commerce.checkout, commerce.cart_physical, commerce.digital_content, commerce.services_booking, commerce.subscription, payments.bot_invoice, payments.telegram_stars]
always: false
products: []
stacks: [nextjs, bot]
---

# Seller details are shown before the order

*Сведения о продавце — до оформления заказа*

## Why

In a distance sale the buyer sees who the seller is before the contract (`ru:svedeniya-o-prodavce-pri-distancionnoy-prodazhe`).

## Incorrect

```tsx
<Checkout /> {/* seller details only in a PDF */}
```

## Correct

```tsx
<Checkout /> <a href="/legal/requisites">Продавец и реквизиты</a>
```

## In your stack

- [nextjs](../stacks/nextjs.md#footer-and-links)
- [bot](../stacks/bot.md#footer-and-bot-profile)
