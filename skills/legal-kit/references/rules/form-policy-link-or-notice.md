---
id: form-policy-link-or-notice
title_ru: "У формы с ПДн — ссылка на политику или уведомление"
title_en: "Every personal-data form links to the privacy policy"
reqs: [ru:informirovanie-pri-sbore-pdn, ru:politika-obrabotki-pdn]
basis: norm
features: [forms.contact, forms.registration, forms.generic, commerce.checkout, commerce.services_booking]
always: false
products: []
stacks: [nextjs, static-html]
---

# Every personal-data form links to the privacy policy

*У формы с ПДн — ссылка на политику или уведомление*

## Why

The operator publishes its policy and tells the person what is collected and why at the point of collection (`ru:politika-obrabotki-pdn`, `ru:informirovanie-pri-sbore-pdn`). A form that collects data with no link leaves the user uninformed.

## Incorrect

```html
<form action="/lead"><input name="phone"><button>Send</button></form>
```

## Correct

```html
<form action="/lead"><input name="phone">
  <p>Отправляя форму, вы соглашаетесь с <a href="/legal/privacy">политикой</a>.</p>
  <button>Отправить</button></form>
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
- [static-html](../stacks/static-html.md#consent-checkbox-in-forms)
