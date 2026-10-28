---
id: analytics-after-consent
title_ru: "Счётчики и пиксели загружаются только после согласия"
title_en: "Counters and pixels load only after consent"
reqs: [ru:soglasie-na-analitiku-i-cookies, ru:cookies-i-identifikatory-kak-pdn]
basis: practice
features: [analytics.web_counter, analytics.session_replay, analytics.tag_manager, ads.pixels, ads.pixels_foreign, bot.mini_app]
always: false
products: []
stacks: [nextjs, react, static-html]
---

# Counters and pixels load only after consent

*Счётчики и пиксели загружаются только после согласия*

## Why

Identifiers that counters collect are treated as personal data in court practice, and the processing needs a ground (`ru:soglasie-na-analitiku-i-cookies`). Holding the script until consent is the engineering way to make the ground real.

## Incorrect

```tsx
<Script src="https://mc.yandex.ru/metrika/tag.js" strategy="afterInteractive" />
```

## Correct

```tsx
{consent.analytics && <Script src="https://mc.yandex.ru/metrika/tag.js" />}
```

## In your stack

- [nextjs](../stacks/nextjs.md#analytics-gated-by-consent)
- [react](../stacks/react.md#analytics-gated-by-consent)
- [static-html](../stacks/static-html.md#analytics-gated-by-consent)
