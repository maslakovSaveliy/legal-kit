---
id: banner-reject-equal-to-accept
title_ru: "В баннере «Отклонить» не слабее «Принять»"
title_en: "Reject is as easy as Accept in the banner"
reqs: [ru:soglasie-na-analitiku-i-cookies]
basis: interpretation
features: [analytics.web_counter, analytics.session_replay, analytics.tag_manager, ads.pixels, ads.pixels_foreign]
always: false
products: []
stacks: [nextjs, static-html]
---

# Reject is as easy as Accept in the banner

*В баннере «Отклонить» не слабее «Принять»*

## Why

Consent obtained by a hidden or tiny refusal is hard to defend as given freely; this is a reading of the consent rules, not a separate norm (`ru:soglasie-na-analitiku-i-cookies`).

## Incorrect

```html
<button class="big">Принять</button> <a class="tiny">настройки</a>
```

## Correct

```html
<button>Принять</button> <button>Отклонить</button>
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-banner)
- [static-html](../stacks/static-html.md#consent-banner)
