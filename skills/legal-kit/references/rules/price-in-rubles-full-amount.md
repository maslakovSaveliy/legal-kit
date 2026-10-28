---
id: price-in-rubles-full-amount
title_ru: "Цена — в рублях и полной суммой"
title_en: "Prices are shown in roubles as the full amount"
reqs: [ru:cena-v-rublyah-i-polnaya-summa]
basis: norm
features: [commerce.checkout, commerce.cart_physical, commerce.digital_content, commerce.services_booking, commerce.subscription]
always: false
products: []
stacks: [nextjs]
---

# Prices are shown in roubles as the full amount

*Цена — в рублях и полной суммой*

## Why

The consumer sees the full price in roubles before buying, with no amounts added later in the flow (`ru:cena-v-rublyah-i-polnaya-summa`).

## Incorrect

```tsx
<Price value={item.usd} currency="USD" /> {/* + fee at checkout */}
```

## Correct

```tsx
<Price value={item.totalRub} currency="RUB" />
```

## In your stack

- [nextjs](../stacks/nextjs.md#footer-and-links)
