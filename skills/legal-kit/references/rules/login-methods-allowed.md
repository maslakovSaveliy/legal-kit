---
id: login-methods-allowed
title_ru: "Вход — допустимыми способами"
title_en: "Sign-in uses the allowed methods"
reqs: [ru:sposoby-avtorizacii-polzovateley]
basis: norm
features: [forms.registration, auth.google, auth.apple, auth.facebook, auth.telegram, auth.sms_otp, auth.vk_id, auth.yandex_id, auth.gosuslugi, bot.mini_app]
always: false
products: []
stacks: [nextjs]
---

# Sign-in uses the allowed methods

*Вход — допустимыми способами*

## Why

A Russian owner that opens content only after sign-in authorizes users from Russia by the methods the law lists (`ru:sposoby-avtorizacii-polzovateley`). A foreign sign-in as the only method is the risky case.

## Incorrect

```tsx
<SignIn providers={['google']} />
```

## Correct

```tsx
<SignIn providers={['phone', 'vkid', 'yandex']} />
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-checkbox-in-forms)
