---
id: form-minimal-fields
title_ru: "Форма спрашивает только то, что нужно для цели"
title_en: "Forms ask only for what the purpose needs"
reqs: [ru:informirovanie-pri-sbore-pdn]
basis: practice
features: [forms.contact, forms.registration, forms.generic]
always: false
products: []
stacks: [nextjs]
---

# Forms ask only for what the purpose needs

*Форма спрашивает только то, что нужно для цели*

## Why

Every extra field is extra personal data to justify, protect and list in the policy. Keeping the form to the purpose keeps the documents short and the risk small (`ru:informirovanie-pri-sbore-pdn`).

## Incorrect

```tsx
<Input name="passport" />  {/* not needed for a call-back */}
```

## Correct

```tsx
<Input name="name" /> <Input name="phone" />
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
