---
id: bot-phone-after-consent
title_ru: "Телефон в боте — только после согласия"
title_en: "A bot asks for the phone only after consent"
reqs: [ru:dokumenty-i-soglasiya-v-chat-bote, ru:soglasie-na-obrabotku-pdn]
basis: interpretation
features: [bot.telegram, bot.max, bot.mini_app]
always: false
products: [bot]
stacks: [bot]
---

# A bot asks for the phone only after consent

*Телефон в боте — только после согласия*

## Why

Asking for a contact on the first message collects data before the user saw the policy or consented (`ru:dokumenty-i-soglasiya-v-chat-bote`).

## Incorrect

```py
@router.message(CommandStart())
async def start(m): await m.answer("Номер?", reply_markup=contact_keyboard())
```

## Correct

```py
@router.callback_query(F.data == "consent:grant")
async def granted(c): await c.message.answer("Номер?", reply_markup=contact_keyboard())
```

## In your stack

- [bot](../stacks/bot.md#consent-checkbox-in-the-chat)
