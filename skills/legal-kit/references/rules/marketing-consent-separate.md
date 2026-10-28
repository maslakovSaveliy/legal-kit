---
id: marketing-consent-separate
title_ru: "Согласие на рассылку — отдельно и до первой рассылки"
title_en: "Marketing consent is separate and comes before the first mailing"
reqs: [ru:soglasie-na-reklamu-po-setyam-elektrosvyazi]
basis: norm
features: [comms.email_marketing, comms.sms, comms.push, bot.telegram, bot.max, bot.mini_app]
always: false
products: []
stacks: [nextjs, bot]
---

# Marketing consent is separate and comes before the first mailing

*Согласие на рассылку — отдельно и до первой рассылки*

## Why

Advertising by e-mail, SMS or messages needs the recipient's prior consent to receive it (`ru:soglasie-na-reklamu-po-setyam-elektrosvyazi`). Consent to data processing is not consent to advertising.

## Incorrect

```ts
await mailer.subscribe(user.email) // after registration
```

## Correct

```ts
if (form.marketingConsent) await mailer.subscribe(user.email)
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
