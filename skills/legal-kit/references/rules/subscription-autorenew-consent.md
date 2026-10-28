---
id: subscription-autorenew-consent
title_ru: "Автопродление — с отдельным согласием и уведомлениями"
title_en: "Auto-renewal needs its own consent and notices"
reqs: [ru:avtospisaniya-po-podpiskam]
basis: norm
features: [commerce.subscription, commerce.trial, mobile.iap]
always: false
products: []
stacks: [nextjs]
---

# Auto-renewal needs its own consent and notices

*Автопродление — с отдельным согласием и уведомлениями*

## Why

Recurring charges need the consumer's consent to them and a way to stop them (`ru:avtospisaniya-po-podpiskam`).

## Incorrect

```ts
await billing.subscribe(user, plan, { autoRenew: true }) // implied
```

## Correct

```ts
if (form.autoRenewConsent) await billing.subscribe(user, plan, { autoRenew: true })
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
