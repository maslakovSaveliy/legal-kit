# Rules library

Contents: [Forms and consent](#forms-and-consent) | [Analytics and SDKs](#analytics-and-sdks) | [Where data goes](#where-data-goes) | [Sales, payments, subscriptions](#sales-payments-subscriptions) | [Owner details, advertising, sign-in](#owner-details-advertising-sign-in) | [Bots and mini apps](#bots-and-mini-apps) | [Mobile apps](#mobile-apps)

One rule per file, for agents that write code. Each rule names the requirement ids of the knowledge pack it rests on (`reqs`) and a basis: `norm` (law or bylaw), `practice` (engineering), `interpretation` (a reading of the rules) or `platform` (a store or messenger rule, not Russian law). The `rules.py` script picks the rules whose requirements apply to the project and writes `.legal/RULES.md`; the label it prints is never stronger than the requirement allows. Norms, deadlines and amounts live in the requirement records, never in a rule.

## Forms and consent

| Rule | Basis | Requirements |
|---|---|---|
| [Personal-data consent is a separate, unticked checkbox](consent-separate-checkbox.md) | norm | `ru:soglasie-na-obrabotku-pdn` |
| [Consent is not bundled with accepting the offer](consent-not-bundled-with-offer.md) | norm | `ru:soglasie-na-obrabotku-pdn`, `ru:akcept-polzovatelskogo-soglasheniya` |
| [Every personal-data form links to the privacy policy](form-policy-link-or-notice.md) | norm | `ru:informirovanie-pri-sbore-pdn`, `ru:politika-obrabotki-pdn` |
| [Forms ask only for what the purpose needs](form-minimal-fields.md) | practice | `ru:informirovanie-pri-sbore-pdn` |
| [The consent log is append-only](consent-log-append-only.md) | practice | `ru:soglasie-na-obrabotku-pdn` |

## Analytics and SDKs

| Rule | Basis | Requirements |
|---|---|---|
| [Counters and pixels load only after consent](analytics-after-consent.md) | practice | `ru:soglasie-na-analitiku-i-cookies`, `ru:cookies-i-identifikatory-kak-pdn` |
| [A new SDK goes through the existing consent gate](sdk-through-consent-gate.md) | practice | `ru:postavshchiki-analitiki-i-sdk` |
| [Reject is as easy as Accept in the banner](banner-reject-equal-to-accept.md) | interpretation | `ru:soglasie-na-analitiku-i-cookies` |

## Where data goes

| Rule | Basis | Requirements |
|---|---|---|
| [Russian users' data is written to a database in Russia](data-stored-in-russia.md) | norm | `ru:lokalizaciya-pdn` |
| [A foreign data recipient needs a processing agreement and a notice](foreign-processor-needs-notice.md) | norm | `ru:transgranichnaya-peredacha-pdn`, `ru:poruchenie-obrabotki-pdn` |

## Sales, payments, subscriptions

| Rule | Basis | Requirements |
|---|---|---|
| [A paid add-on is never pre-selected](paid-addon-not-prechecked.md) | norm | `ru:soglasie-na-platnye-dopolnitelnye-uslugi` |
| [Prices are shown in roubles as the full amount](price-in-rubles-full-amount.md) | norm | `ru:cena-v-rublyah-i-polnaya-summa` |
| [The price does not depend on the payment method](same-price-any-payment-method.md) | norm | `ru:edinaya-cena-nezavisimo-ot-sposoba-oplaty` |
| [The offer is accepted by an explicit action](offer-accepted-by-explicit-action.md) | norm | `ru:akcept-polzovatelskogo-soglasheniya`, `ru:publichnaya-oferta-i-podtverzhdenie-zakaza` |
| [The buyer gets an order confirmation](order-confirmation-sent.md) | norm | `ru:publichnaya-oferta-i-podtverzhdenie-zakaza` |
| [The receipt contact is collected before payment](receipt-contact-before-payment.md) | norm | `ru:onlayn-kkt-i-elektronnyy-chek` |
| [Auto-renewal needs its own consent and notices](subscription-autorenew-consent.md) | norm | `ru:avtospisaniya-po-podpiskam` |
| [A subscription can be cancelled in the product](subscription-cancel-easy.md) | norm | `ru:otkaz-ot-uslug-i-cifrovyh-podpisok` |
| [Seller details are shown before the order](seller-details-before-order.md) | norm | `ru:svedeniya-o-prodavce-pri-distancionnoy-prodazhe` |
| [The Ministry's root certificate is trusted by the backend when the acquirer needs it](acquirer-nuc-root-in-truststore.md) | practice | `ru:trebovaniya-ekvayerov-k-sertifikatam-nuc` |

## Owner details, advertising, sign-in

| Rule | Basis | Requirements |
|---|---|---|
| [Owner details are in the footer and on a requisites page](owner-details-in-footer.md) | norm | `ru:svedeniya-o-vladelce-sayta` |
| [Marketing consent is separate and comes before the first mailing](marketing-consent-separate.md) | norm | `ru:soglasie-na-reklamu-po-setyam-elektrosvyazi` |
| [Ads carry the label and the erid token](ad-marking-erid.md) | norm | `ru:pometka-reklama-i-svedeniya-o-reklamodatele`, `ru:identifikator-reklamy-erid` |
| [Sign-in uses the allowed methods](login-methods-allowed.md) | norm | `ru:sposoby-avtorizacii-polzovateley` |

## Bots and mini apps

| Rule | Basis | Requirements |
|---|---|---|
| [In a bot, the offer and the consent are two actions](bot-two-actions-offer-and-consent.md) | interpretation | `ru:dokumenty-i-soglasiya-v-chat-bote` |
| [A bot asks for the phone only after consent](bot-phone-after-consent.md) | interpretation | `ru:dokumenty-i-soglasiya-v-chat-bote`, `ru:soglasie-na-obrabotku-pdn` |
| [Documents are reachable from the bot](bot-documents-reachable.md) | interpretation | `ru:dokumenty-i-soglasiya-v-chat-bote`, `ru:politika-obrabotki-pdn` |
| [A bot asks for the receipt contact before the invoice](bot-receipt-contact-before-invoice.md) | interpretation | `ru:oplata-v-chat-bote-i-chek` |
| [Bot data lives on the owner's server in Russia, not in platform storage](bot-store-data-on-own-server.md) | interpretation | `ru:pdn-pri-sbore-cherez-inostrannyy-messendzher` |
| [The bot's own privacy policy is set on the platform](bot-platform-privacy-policy.md) | platform rule | `ru:pravila-platform-botov-dannye-i-dopusk` |
| [Digital goods in a Telegram bot are sold for Stars](bot-digital-goods-stars.md) | platform rule | `ru:pravila-platform-botov-oplata` |

## Mobile apps

| Rule | Basis | Requirements |
|---|---|---|
| [Account deletion is available inside the app](mobile-account-deletion.md) | platform rule | `ru:pravila-storov-akkaunty-i-vhod` |
