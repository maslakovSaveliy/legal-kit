---
id: data-stored-in-russia
title_ru: "Данные пользователей из РФ пишутся в базу в России"
title_en: "Russian users' data is written to a database in Russia"
reqs: [ru:lokalizaciya-pdn]
basis: norm
features: []
always: true
products: []
stacks: [nextjs, python, bot]
---

# Russian users' data is written to a database in Russia

*Данные пользователей из РФ пишутся в базу в России*

## Why

Recording and storing personal data of Russian citizens in databases outside Russia is not allowed (`ru:lokalizaciya-pdn`). Where the first write lands is decided by the configuration of the database and the hosting.

## Incorrect

```env
DATABASE_URL=postgres://user@db.eu-central-1.example.com/shop
```

## Correct

```env
DATABASE_URL=postgres://user@db.ru-msk.example.ru/shop
```

## In your stack

- [nextjs](../stacks/nextjs.md#consent-log-existing-backend-only)
- [python](../stacks/python.md#consent-log-existing-backend-only)
- [bot](../stacks/bot.md#consent-log-existing-backend-only)
