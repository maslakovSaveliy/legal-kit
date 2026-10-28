---
id: consent-log-append-only
title_ru: "Журнал согласий только дописывается"
title_en: "The consent log is append-only"
reqs: [ru:soglasie-na-obrabotku-pdn]
basis: practice
features: [forms.contact, forms.registration, forms.generic, commerce.checkout, bot.telegram, bot.max, bot.mini_app]
always: false
products: []
stacks: [nextjs, python, bot]
---

# The consent log is append-only

*Журнал согласий только дописывается*

## Why

The operator has to prove that consent was given (`ru:soglasie-na-obrabotku-pdn`). A log that records grant and revoke events with the text version, and is never updated in place, is that proof.

## Incorrect

```ts
await db.consent.update({ where: { userId }, data: { granted: false } })
```

## Correct

```ts
await db.consentLog.create({ data: { subjectId, consentVersion, formId, channel, action } })
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-log-existing-backend-only)
- [python](../stacks/python.md#consent-log-existing-backend-only)
- [bot](../stacks/bot.md#consent-log-existing-backend-only)
