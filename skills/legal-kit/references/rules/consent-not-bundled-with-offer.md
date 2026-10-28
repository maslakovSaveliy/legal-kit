---
id: consent-not-bundled-with-offer
title_ru: "Согласие на ПДн не совмещено с принятием оферты"
title_en: "Consent is not bundled with accepting the offer"
reqs: [ru:soglasie-na-obrabotku-pdn, ru:akcept-polzovatelskogo-soglasheniya]
basis: norm
features: [forms.contact, forms.registration, forms.generic, commerce.checkout, commerce.subscription]
always: false
products: []
stacks: [nextjs, bot]
---

# Consent is not bundled with accepting the offer

*Согласие на ПДн не совмещено с принятием оферты*

## Why

Accepting a contract and consenting to data processing are two different acts with different grounds; one box or one button for both makes it impossible to show which of them the user gave (`ru:soglasie-na-obrabotku-pdn`, `ru:akcept-polzovatelskogo-soglasheniya`).

## Incorrect

```tsx
<Checkbox label="Принимаю оферту и согласен на обработку данных" />
```

## Correct

```tsx
<Checkbox name="acceptOffer" label="Принимаю условия оферты" />
<Checkbox name="consentPd" label="Согласен на обработку персональных данных" />
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
