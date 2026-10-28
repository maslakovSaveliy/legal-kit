---
id: mobile-account-deletion
title_ru: "Удаление аккаунта — внутри приложения"
title_en: "Account deletion is available inside the app"
reqs: [ru:pravila-storov-akkaunty-i-vhod]
basis: platform
features: [mobile.app, forms.registration]
always: false
products: [ios, android]
stacks: [react-native, swift, flutter]
---

# Account deletion is available inside the app

*Удаление аккаунта — внутри приложения*

## Why

App stores require an in-app way to delete an account when the app lets users create one; this is a store rule, not Russian law (`ru:pravila-storov-akkaunty-i-vhod`).

## Incorrect

```tsx
<Text>To delete your account, e-mail support</Text>
```

## Correct

```tsx
<Button title="Удалить аккаунт" onPress={deleteAccount} />
```

## In your stack

- [react-native](../stacks/react-native.md#legal-pages)
- [swift](../stacks/swift.md#legal-pages)
- [flutter](../stacks/flutter.md#legal-pages)
