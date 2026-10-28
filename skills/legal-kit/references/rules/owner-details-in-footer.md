---
id: owner-details-in-footer
title_ru: "Сведения о владельце — в подвале и на странице реквизитов"
title_en: "Owner details are in the footer and on a requisites page"
reqs: [ru:svedeniya-o-vladelce-sayta]
basis: norm
features: []
always: true
products: [site, webapp]
stacks: [nextjs, static-html]
---

# Owner details are in the footer and on a requisites page

*Сведения о владельце — в подвале и на странице реквизитов*

## Why

The owner of a site places information about itself on the site (`ru:svedeniya-o-vladelce-sayta`). A short footer line and a full requisites page cover it without cluttering every page.

## Incorrect

```tsx
<footer>© Shop</footer>
```

## Correct

```tsx
<footer>{owner.name} · <a href="/legal/requisites">Реквизиты</a></footer>
```

## In your stack

- [nextjs](../stacks/nextjs.md#footer-and-links)
- [static-html](../stacks/static-html.md#footer-and-links)
