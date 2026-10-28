---
id: offer-accepted-by-explicit-action
title_ru: "Оферта принимается явным действием"
title_en: "The offer is accepted by an explicit action"
reqs: [ru:akcept-polzovatelskogo-soglasheniya, ru:publichnaya-oferta-i-podtverzhdenie-zakaza]
basis: norm
features: [commerce.checkout, commerce.cart_physical, commerce.digital_content, commerce.services_booking, commerce.subscription, forms.registration, bot.telegram, bot.max, bot.mini_app]
always: false
products: []
stacks: [nextjs, bot]
---

# The offer is accepted by an explicit action

*Оферта принимается явным действием*

## Why

Acceptance is a clear action after the terms were shown; silence or simply continuing to use the product is a weak basis (`ru:akcept-polzovatelskogo-soglasheniya`, `ru:publichnaya-oferta-i-podtverzhdenie-zakaza`).

## Incorrect

```tsx
<p>Продолжая пользоваться сайтом, вы принимаете оферту</p>
```

## Correct

```tsx
<Checkbox name="acceptOffer" required label="Принимаю условия" /> <a href="/legal/offer">Оферта</a>
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
