---
id: bot-documents-reachable
title_ru: "Документы доступны из бота"
title_en: "Documents are reachable from the bot"
reqs: [ru:dokumenty-i-soglasiya-v-chat-bote, ru:politika-obrabotki-pdn]
basis: interpretation
features: [bot.telegram, bot.max, bot.mini_app]
always: false
products: [bot]
stacks: [bot]
---

# Documents are reachable from the bot

*Документы доступны из бота*

## Why

The policy is published with unrestricted access; in a bot that means a command or menu button with links (`ru:politika-obrabotki-pdn`, `ru:dokumenty-i-soglasiya-v-chat-bote`).

## Incorrect

```py
# no /privacy command, no links in the description
```

## Correct

```py
@router.message(Command("privacy"))
async def privacy(m): await m.answer(POLICY_URL)
```

## In your stack

- [bot](../stacks/bot.md#legal-pages)
