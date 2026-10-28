---
id: foreign-processor-needs-notice
title_ru: "Иностранный получатель данных — поручение и уведомление"
title_en: "A foreign data recipient needs a processing agreement and a notice"
reqs: [ru:transgranichnaya-peredacha-pdn, ru:poruchenie-obrabotki-pdn]
basis: norm
features: [foreign.data_processors, chat.widget, ads.pixels_foreign, analytics.mobile_sdk]
always: false
products: []
stacks: [nextjs]
---

# A foreign data recipient needs a processing agreement and a notice

*Иностранный получатель данных — поручение и уведомление*

## Why

Sending personal data to a foreign recipient requires a prior notice to the regulator, and a processor acting for the owner needs a processing agreement (`ru:transgranichnaya-peredacha-pdn`, `ru:poruchenie-obrabotki-pdn`). Adding such a vendor in code is a legal step, not only a technical one.

## Incorrect

```ts
await fetch('https://api.foreign-crm.example.com/leads', { method: 'POST', body })
```

## Correct

```ts
// recipient listed in the policy; notice filed; processing agreement signed
await crm.createLead(body)
```

## In your stack

- [nextjs](../stacks/nextjs.md#legal-pages)
