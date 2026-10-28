---
id: sdk-through-consent-gate
title_ru: "Новый SDK подключается через существующий механизм согласия"
title_en: "A new SDK goes through the existing consent gate"
reqs: [ru:postavshchiki-analitiki-i-sdk]
basis: practice
features: [analytics.mobile_sdk, ads.pixels_foreign, analytics.web_counter, analytics.session_replay, analytics.tag_manager, ads.pixels, ads.pixels_foreign]
always: false
products: []
stacks: [react-native, nextjs]
---

# A new SDK goes through the existing consent gate

*Новый SDK подключается через существующий механизм согласия*

## Why

Each analytics or ad vendor receives user data and becomes a party the policy has to name (`ru:postavshchiki-analitiki-i-sdk`). Adding it outside the consent gate silently breaks the gate the project already has.

## Incorrect

```ts
AppMetrica.activate({ apiKey }) // at app start
```

## Correct

```ts
if (await consent.has('analytics')) AppMetrica.activate({ apiKey })
```

## In your stack

- [react-native](../stacks/react-native.md#analytics-gated-by-consent)
- [nextjs](../stacks/nextjs.md#analytics-gated-by-consent)
