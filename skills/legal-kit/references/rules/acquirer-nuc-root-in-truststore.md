---
id: acquirer-nuc-root-in-truststore
title_ru: "Корень Минцифры — в trust store бэка, если банк его требует"
title_en: "The Ministry's root certificate is trusted by the backend when the acquirer needs it"
reqs: [ru:trebovaniya-ekvayerov-k-sertifikatam-nuc]
basis: practice
features: [payments.tbank, bot.max]
always: false
products: []
stacks: [python, nextjs, bot]
---

# The Ministry's root certificate is trusted by the backend when the acquirer needs it

*Корень Минцифры — в trust store бэка, если банк его требует*

## Why

Some acquirers and the MAX API serve certificates chained to the Russian Trusted Root CA; a backend that does not trust it fails the TLS handshake and payments stop. This is the bank's or platform's requirement, not a norm (`ru:trebovaniya-ekvayerov-k-sertifikatam-nuc`).

## Incorrect

```py
requests.post(ACQUIRER_URL, json=payload, verify=False)
```

## Correct

```py
requests.post(ACQUIRER_URL, json=payload, verify='/etc/ssl/certs/ca-with-russian-trusted-root.pem')
```

## In your stack

- [python](../stacks/python.md#verify-and-record-state)
- [bot](../stacks/bot.md#detect)
