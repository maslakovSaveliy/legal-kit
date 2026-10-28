---
id: paid-addon-not-prechecked
title_ru: "Платная доп. опция не отмечена заранее"
title_en: "A paid add-on is never pre-selected"
reqs: [ru:soglasie-na-platnye-dopolnitelnye-uslugi]
basis: norm
features: [commerce.checkout, commerce.cart_physical, commerce.digital_content, commerce.services_booking, commerce.subscription]
always: false
products: []
stacks: [nextjs, react]
---

# A paid add-on is never pre-selected

*Платная доп. опция не отмечена заранее*

## Why

An additional paid good or service needs the buyer's own consent; a pre-ticked add-on is not that consent (`ru:soglasie-na-platnye-dopolnitelnye-uslugi`).

## Incorrect

```tsx
<Checkbox name="giftWrap" defaultChecked label="Подарочная упаковка" />
```

## Correct

```tsx
<Checkbox name="giftWrap" label="Подарочная упаковка (платно)" />
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
- [react](../stacks/react.md#consent-checkbox-in-forms)
