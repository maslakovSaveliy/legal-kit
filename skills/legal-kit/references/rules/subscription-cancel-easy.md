---
id: subscription-cancel-easy
title_ru: "Подписку можно отменить в продукте"
title_en: "A subscription can be cancelled in the product"
reqs: [ru:otkaz-ot-uslug-i-cifrovyh-podpisok]
basis: norm
features: [commerce.subscription, commerce.digital_content]
always: false
products: []
stacks: [nextjs]
---

# A subscription can be cancelled in the product

*Подписку можно отменить в продукте*

## Why

The consumer may refuse a service or a digital subscription; the product gives a direct way to do it (`ru:otkaz-ot-uslug-i-cifrovyh-podpisok`).

## Incorrect

```tsx
<p>Для отмены напишите в поддержку</p>
```

## Correct

```tsx
<Button onClick={cancelSubscription}>Отменить подписку</Button>
```

## In your stack

- [nextjs](../stacks/nextjs.md#legal-pages)
