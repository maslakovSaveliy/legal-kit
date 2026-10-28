---
id: consent-separate-checkbox
title_ru: "Согласие на ПДн — отдельный чекбокс без предотметки"
title_en: "Personal-data consent is a separate, unticked checkbox"
reqs: [ru:soglasie-na-obrabotku-pdn]
basis: norm
features: [forms.contact, forms.registration, forms.generic, commerce.checkout, commerce.services_booking, chat.widget]
always: false
products: []
stacks: [nextjs, react, static-html]
---

# Personal-data consent is a separate, unticked checkbox

*Согласие на ПДн — отдельный чекбокс без предотметки*

## Why

When a form rests on consent, the consent must be specific, informed and given by the user's own action, and it is drawn up separately from other texts the user confirms (`ru:soglasie-na-obrabotku-pdn`). A ticked-by-default box or a box hidden in the terms is not such an action.

## Incorrect

```tsx
<input type="checkbox" name="consent" defaultChecked />
<label>I agree with everything</label>
```

## Correct

```tsx
<input type="checkbox" name="consentPd" required={needsConsent} />
<label>Согласен на обработку персональных данных</label>
<a href="/legal/privacy">Политика</a>
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
- [react](../stacks/react.md#consent-checkbox-in-forms)
- [static-html](../stacks/static-html.md#consent-checkbox-in-forms)
