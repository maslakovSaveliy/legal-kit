---
id: same-price-any-payment-method
title_ru: "Цена не зависит от способа оплаты"
title_en: "The price does not depend on the payment method"
reqs: [ru:edinaya-cena-nezavisimo-ot-sposoba-oplaty]
basis: norm
features: [payments.yookassa, payments.cloudpayments, payments.tbank, payments.robokassa, payments.sbp, payments.bnpl]
always: false
products: []
stacks: [nextjs]
---

# The price does not depend on the payment method

*Цена не зависит от способа оплаты*

## Why

A different price for card, transfer or another method is not allowed for consumers (`ru:edinaya-cena-nezavisimo-ot-sposoba-oplaty`).

## Incorrect

```ts
const total = method === 'card' ? price * cardMarkup : price
```

## Correct

```ts
const total = price
```

## In your stack

- [nextjs](../stacks/nextjs.md#footer-and-links)
