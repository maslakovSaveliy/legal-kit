---
id: ad-marking-erid
title_ru: "Реклама размечена: пометка и erid"
title_en: "Ads carry the label and the erid token"
reqs: [ru:pometka-reklama-i-svedeniya-o-reklamodatele, ru:identifikator-reklamy-erid]
basis: norm
features: [ads.own_site_promo]
always: false
products: []
stacks: [nextjs]
---

# Ads carry the label and the erid token

*Реклама размечена: пометка и erid*

## Why

Internet advertising carries the word «Реклама», the advertiser and the ad identifier (`ru:pometka-reklama-i-svedeniya-o-reklamodatele`, `ru:identifikator-reklamy-erid`).

## Incorrect

```tsx
<a href="https://partner.example/?utm=x"><img src="/banner.png" /></a>
```

## Correct

```tsx
<a href="https://partner.example/?erid=TOKEN">Реклама · ООО «Партнёр»<img src="/banner.png" /></a>
```

## In your stack

- [nextjs](../stacks/nextjs.md#footer-and-links)
