"""Checks for the jurisdiction-neutral feature catalog.

The catalog (skills/legal-kit/references/features/catalog.json) lists signals
that detect product features in source code and on a live site. It carries no
legal content. Stdlib + pytest only; paths are resolved from this file, so the
test runs from any directory.

Matching rules used here (and expected from the scanners):
- deps: exact package name as a whole token in a dependency manifest.
- code: Python `re`, searched in any text file (each pattern compiled alone).
- dom: Python `re`, searched in HTML-like files and in live page HTML.
- hosts: `host[/path-prefix]`; matches a URL when the URL host equals the host
  or is a subdomain of it, and the URL path starts with the path prefix.
"""

import json
import re
import time
import warnings
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "skills" / "legal-kit" / "references" / "features" / "catalog.json"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "catalog"

REQUIRED_KEYS = ("id", "title_ru", "title_en", "deps", "code", "hosts", "dom", "stacks")
OPTIONAL_KEYS = ("notes",)
ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?(/[A-Za-z0-9_@./-]*)?$")
SIGNAL_KEYS = ("deps", "code", "hosts", "dom")
STACKS = (
    "nextjs", "react", "nestjs", "react-native", "flutter", "swift",
    "python", "static-html", "generic-web", "no-code",
)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

# Ids named in the task brief. The catalog may hold more; none may be missing.
EXPECTED_IDS = (
    "forms.contact", "forms.registration",
    "auth.vk_id", "auth.yandex_id", "auth.gosuslugi", "auth.google", "auth.apple", "auth.sms_otp",
    "commerce.cart_physical", "commerce.marked_goods", "commerce.digital_content",
    "commerce.services_booking", "commerce.prepayment", "commerce.subscription",
    "commerce.trial", "commerce.promo_codes", "commerce.loyalty_points", "commerce.gift_cards",
    "payments.yookassa", "payments.cloudpayments", "payments.tbank", "payments.robokassa",
    "payments.sbp", "payments.stripe", "payments.paddle", "payments.receipts_kkt",
    "platform.marketplace",
    "analytics.web_counter", "analytics.session_replay", "ads.pixels", "analytics.tag_manager",
    "analytics.mobile_sdk",
    "chat.widget",
    "comms.email_marketing", "comms.push", "comms.sms", "comms.calls_calltracking",
    "ugc.reviews", "ugc.user_messaging", "ugc.public_profiles", "ugc.uploads",
    "content.webinars",
    "audience.kids", "audience.adult_18",
    "sector.education_courses", "sector.medical", "sector.finance", "sector.gambling",
    "sector.alcohol_tobacco", "sector.gov", "sector.taxi_tourism",
    "tech.generative_ai",
    "mobile.app", "mobile.iap", "mobile.att",
    "foreign.fonts", "foreign.captcha", "foreign.cdn_hosting", "foreign.embeds",
    "captcha.smartcaptcha",
    "ads.own_site_promo", "content.meta_symbols", "content.vpn_mentions",
    "i18n.foreign_language_ui",
)

# Keyword-based features: weak evidence, the owner must confirm.
WEAK_PREFIXES = ("sector.", "audience.")
WEAK_IDS = ("content.vpn_mentions", "i18n.foreign_language_ui")

# Legal content never belongs to the catalog.
LEGAL_RE = re.compile(
    r"\bст\.\s*\d|\b\d{2,3}-ФЗ\b|\bФЗ\b|\b\d{2,3}-FZ\b|Federal Law|\bArt\.\s*\d|\bpenalt|\bfines?\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
PRIVACY_PATTERNS = ("raw/articles", "raw/notes", "[[", "../topics/", "/Us" + "ers/", "llm" + "-wiki",
                    "wiki/concepts", "wiki/references")

MANIFEST_NAMES = {
    "package.json", "requirements.txt", "pyproject.toml", "Pipfile", "pubspec.yaml", "Podfile",
    "Package.swift", "build.gradle", "build.gradle.kts", "Gemfile", "composer.json",
}
HTML_SUFFIXES = {
    ".html", ".htm", ".jinja", ".jinja2", ".twig", ".vue", ".tsx", ".jsx", ".php", ".erb",
    ".hbs", ".ejs", ".njk", ".svelte", ".astro",
}
URL_RE = re.compile(r"(?:https?:)?//([A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,})(/[^\s\"'<>)\]}`]*)?")


# --------------------------------------------------------------------- helpers

@lru_cache(maxsize=1)
def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def compiled():
    """Per feature id: (entry, compiled code regexes, compiled dom regexes)."""
    out = {}
    for entry in load_catalog():
        out[entry["id"]] = (
            entry,
            [re.compile(p) for p in entry["code"]],
            [re.compile(p) for p in entry["dom"]],
        )
    return out


def dep_in_manifest(dep, text):
    pattern = r"(?<![\w.@/-])" + re.escape(dep) + r"(?![\w-])"
    return re.search(pattern, text, re.IGNORECASE) is not None


def host_matches(signature, host, path):
    sig_host, _, sig_path = signature.partition("/")
    host = host.lower()
    if not (host == sig_host or host.endswith("." + sig_host)):
        return False
    return not sig_path or path.lstrip("/").lower().startswith(sig_path.lower())


def urls_in(text):
    return [(m.group(1), m.group(2) or "") for m in URL_RE.finditer(text)]


def match_deps(text):
    return {i for i, (e, _, _) in compiled().items() if any(dep_in_manifest(d, text) for d in e["deps"])}


def match_code(text):
    return {i for i, (_, code, _) in compiled().items() if any(rx.search(text) for rx in code)}


def match_dom(text):
    return {i for i, (_, _, dom) in compiled().items() if any(rx.search(text) for rx in dom)}


def match_hosts(text):
    found = set()
    for host, path in urls_in(text):
        for i, (e, _, _) in compiled().items():
            if any(host_matches(sig, host, path) for sig in e["hosts"]):
                found.add(i)
    return found


MATCHERS = {"manifest": match_deps, "code": match_code, "dom": match_dom, "host": match_hosts}
GROUP_TO_KIND = {"deps": "manifest", "code": "code", "hosts": "host", "dom": "dom"}


def detect_file(path):
    """Everything a repo scan would find in one file."""
    text = path.read_text(encoding="utf-8")
    found = match_code(text) | match_hosts(text)
    if path.name in MANIFEST_NAMES:
        found |= match_deps(text)
    if path.suffix.lower() in HTML_SUFFIXES:
        found |= match_dom(text)
    return found


# ------------------------------------------------------------ positive samples
# (feature id, signal kind, sample text). Every non-empty signal group of every
# entry must be exercised by at least one sample of its kind.

POSITIVE_SAMPLES = [
    # forms and accounts
    ("forms.contact", "dom", '<form action="/lead" method="post"><input type="text" name="name"><input type="tel" name="phone"><button>Отправить</button></form>'),
    ("forms.contact", "dom", '<form><textarea name="message"></textarea></form>'),
    ("forms.contact", "code", "export function ContactForm() { return null }"),
    ("forms.registration", "dom", '<input type="password" name="password" autocomplete="new-password">'),
    ("forms.registration", "code", "const cred = await createUserWithEmailAndPassword(auth, email, password);"),
    ("forms.registration", "manifest", "django-allauth==64.0\n"),
    ("auth.vk_id", "manifest", '"@vkid/sdk": "^2.0.0"'),
    ("auth.vk_id", "code", "VKID.Config.init({ app: 1234, redirectUrl: url });"),
    ("auth.vk_id", "host", "https://id.vk.com/authorize?client_id=1"),
    ("auth.vk_id", "dom", '<div id="VkIdSdkOneTap"></div>'),
    ("auth.yandex_id", "manifest", '"passport-yandex": "^0.0.5"'),
    ("auth.yandex_id", "code", "YaAuthSuggest.init(oauthQueryParams, origin);"),
    ("auth.yandex_id", "host", "https://oauth.yandex.ru/authorize?response_type=token"),
    ("auth.yandex_id", "dom", "<button>Войти через Яндекс ID</button>"),
    ("auth.gosuslugi", "manifest", "esia-connector==0.2\n"),
    ("auth.gosuslugi", "code", "esia_client = EsiaClient()"),
    ("auth.gosuslugi", "host", "https://esia.gosuslugi.ru/aas/oauth2/ac?client_id=X"),
    ("auth.gosuslugi", "dom", '<a href="/login/esia">Войти через Госуслуги</a>'),
    ("auth.google", "manifest", '"@react-oauth/google": "^0.12.0"'),
    ("auth.google", "code", "google.accounts.id.initialize({ client_id: ID, callback: cb });"),
    ("auth.google", "host", "https://accounts.google.com/gsi/client"),
    ("auth.google", "dom", '<div id="g_id_onload" data-client_id="X"></div>'),
    ("auth.apple", "manifest", "  sign_in_with_apple: ^6.0.0\n"),
    ("auth.apple", "code", "let provider = ASAuthorizationAppleIDProvider()"),
    ("auth.apple", "host", "https://appleid.cdn-apple.com/appleauth/static/jsapi/appleid/1/en_US/appleid.auth.js"),
    ("auth.apple", "dom", "<button>Sign in with Apple</button>"),
    ("auth.telegram", "manifest", '"react-telegram-login": "^1.1.2"'),
    ("auth.telegram", "code", "window.Telegram.Login.auth({ bot_id: 1 }, cb);"),
    ("auth.telegram", "host", "https://telegram.org/js/telegram-widget.js?22"),
    ("auth.telegram", "dom", '<script async src="https://telegram.org/js/telegram-widget.js?22" data-telegram-login="shop_bot"></script>'),
    ("auth.facebook", "manifest", "pod 'FBSDKLoginKit'\n"),
    ("auth.facebook", "code", "FB.login(function (response) {});"),
    ("auth.facebook", "dom", "<button>Войти через Facebook</button>"),
    ("auth.sms_otp", "code", "await auth().signInWithPhoneNumber(phone);"),
    ("forms.generic", "code", "class EnrollForm(forms.ModelForm):"),
    ("forms.generic", "dom", '<form method="post">\n  {% csrf_token %}\n  {{ form.as_p }}\n</form>'),
    ("auth.sms_otp", "dom", '<input autocomplete="one-time-code" inputmode="numeric">'),
    # commerce
    ("commerce.checkout", "manifest", '"use-shopping-cart": "^3.2.0"'),
    ("commerce.checkout", "code", "const { addToCart } = useCart();"),
    ("commerce.checkout", "host", "https://cdn.snipcart.com/themes/v3.7.0/default/snipcart.js"),
    ("commerce.checkout", "dom", "<button>В корзину</button>"),
    ("commerce.cart_physical", "code", "shipping_address = form.cleaned_data['shipping_address']"),
    ("commerce.cart_physical", "code", "const tariff = await cdekClient.calculate(order);"),
    ("commerce.cart_physical", "host", "https://api.cdek.ru/v2/calculator/tariff"),
    ("commerce.cart_physical", "dom", "<p>Доставка курьером и самовывоз из магазина</p>"),
    ("commerce.cart_physical", "dom", "<h2>Доставка и оплата</h2>"),
    ("commerce.cart_physical", "code", 'TextField("Адрес доставки", text: $address)'),
    ("commerce.cart_physical", "code", "delivery_type = order.delivery_type"),
    ("commerce.checkout", "code", "struct CheckoutView: View {"),
    ("commerce.checkout", "code", 'Button("Оплатить заказ") { Task { await placeOrder() } }'),
    ("commerce.marked_goods", "code", "const km = DataMatrix.parse(raw);"),
    ("commerce.marked_goods", "host", "https://markirovka.crpt.ru/api/v3/true-api/"),
    ("commerce.marked_goods", "dom", "<p>Работаем с системой Честный знак</p>"),
    ("commerce.digital_content", "manifest", '"@lemonsqueezy/lemonsqueezy.js": "^4.0.0"'),
    ("commerce.digital_content", "code", "license_key = generate_license_key(order)"),
    ("commerce.digital_content", "host", "https://gumroad.com/js/gumroad.js"),
    ("commerce.digital_content", "dom", "<p>Ключ активации придёт на e-mail</p>"),
    ("commerce.services_booking", "manifest", '"react-calendly": "^4.3.0"'),
    ("commerce.services_booking", "code", "const available_slots = get_slots(day)"),
    ("commerce.services_booking", "host", "https://w123456.yclients.com/"),
    ("commerce.services_booking", "dom", "<a>Онлайн-запись</a>"),
    ("commerce.services_booking", "code", "class BookingPage extends StatefulWidget {}"),
    ("commerce.services_booking", "code", "child: const Text('Записаться и оплатить'),"),
    ("commerce.prepayment", "code", 'payment_mode: "full_prepayment"'),
    ("commerce.prepayment", "dom", "<p>Предоплата 50% при заказе</p>"),
    ("commerce.subscription", "manifest", "dj-stripe==2.9\n"),
    ("commerce.subscription", "code", "mode: 'subscription',"),
    ("commerce.subscription", "dom", "<p>Автопродление можно отключить в любой момент</p>"),
    ("commerce.subscription", "dom", "<p>Подписка — 299 ₽ в месяц</p>"),
    ("commerce.subscription", "code", 'Text("199 ₽ в месяц. Подписка продлевается автоматически.")'),
    ("commerce.trial", "code", "trial_period_days: 14,"),
    ("commerce.trial", "dom", "<p>Пробный период 7 дней</p>"),
    ("commerce.promo_codes", "code", "applyPromo(code)"),
    ("commerce.promo_codes", "dom", '<input name="promo" placeholder="Промокод">'),
    ("commerce.loyalty_points", "code", "user.loyalty_points += 10"),
    ("commerce.loyalty_points", "host", "https://api.mindbox.ru/v3/operations/async"),
    ("commerce.loyalty_points", "dom", "<p>Спишите бонусные баллы при оплате</p>"),
    ("commerce.gift_cards", "code", "gift_card_code = random_code()"),
    ("commerce.gift_cards", "dom", "<a>Купить подарочный сертификат</a>"),
    ("marketing.giveaways", "code", "giveaway = Giveaway.objects.get(pk=1)"),
    ("marketing.giveaways", "dom", "<h2>Розыгрыш призов среди подписчиков</h2>"),
    # payments
    ("payments.yookassa", "manifest", "yookassa==3.3.0\n"),
    ("payments.yookassa", "code", "const checkout = new window.YooMoneyCheckoutWidget({ confirmation_token });"),
    ("payments.yookassa", "host", "https://yookassa.ru/checkout-widget/v1/checkout-widget.js"),
    ("payments.yookassa", "dom", "<p>Платежи принимает ЮKassa</p>"),
    ("payments.cloudpayments", "manifest", "cloudpayments==1.0\n"),
    ("payments.cloudpayments", "code", "const widget = new cp.CloudPayments();"),
    ("payments.cloudpayments", "host", "https://widget.cloudpayments.ru/bundles/cloudpayments.js"),
    ("payments.cloudpayments", "dom", "<p>Оплата через CloudPayments</p>"),
    ("payments.tbank", "manifest", "pod 'TinkoffASDKUI'\n"),
    ("payments.tbank", "code", 'TerminalKey: "TinkoffBankTest",'),
    ("payments.tbank", "host", "https://securepay.tinkoff.ru/html/payForm/js/tinkoff_v2.js"),
    ("payments.tbank", "dom", '<input type="hidden" name="terminalkey" value="X">'),
    ("payments.robokassa", "manifest", "robokassa==1.0\n"),
    ("payments.robokassa", "code", "url = f'...?MerchantLogin={login}&OutSum={total}'"),
    ("payments.robokassa", "host", "https://auth.robokassa.ru/Merchant/Index.aspx"),
    ("payments.robokassa", "dom", "<p>Оплата через Робокассу</p>"),
    ("payments.sbp", "code", "payment_method = 'sbp_qr'"),
    ("payments.sbp", "host", "https://qr.nspk.ru/AS1000670LSS7DN18SJQDNP4B05KLJL2"),
    ("payments.sbp", "dom", "<span>Оплата по СБП</span>"),
    ("payments.bnpl", "code", "dolyame_client.create(order)"),
    ("payments.bnpl", "host", "https://dolyame.ru/widget/v1/dolyame.js"),
    ("payments.bnpl", "dom", "<button>Оплатить частями</button>"),
    ("payments.stripe", "manifest", '"@stripe/stripe-js": "^4.0.0"'),
    ("payments.stripe", "code", "const stripe = await loadStripe('pk_test_51Habcdefghij');"),
    ("payments.stripe", "host", "https://js.stripe.com/v3/"),
    ("payments.stripe", "dom", '<div class="StripeElement"></div>'),
    ("payments.paddle", "manifest", '"@paddle/paddle-js": "^1.0.0"'),
    ("payments.paddle", "code", "Paddle.Initialize({ token: 'live_x' });"),
    ("payments.paddle", "host", "https://cdn.paddle.com/paddle/v2/paddle.js"),
    ("payments.paddle", "dom", '<a class="paddle_button" href="#">Buy</a>'),
    ("payments.receipts_kkt", "code", "receipt: { tax_system_code: 1, items: [] }"),
    ("payments.receipts_kkt", "host", "https://online.atol.ru/possystem/v4/getToken"),
    ("payments.receipts_kkt", "dom", "<p>Кассовый чек отправим на e-mail</p>"),
    ("platform.marketplace", "manifest", '"@stripe/connect-js": "^3.0.0"'),
    ("platform.marketplace", "code", "application_fee_amount: 123,"),
    ("platform.marketplace", "dom", "<a>Стать продавцом</a>"),
    # analytics and ads
    ("analytics.web_counter", "manifest", '"react-yandex-metrika": "^2.6.0"'),
    ("analytics.web_counter", "code", 'ym(12345678, "init", { clickmap: true });'),
    ("analytics.web_counter", "code", "gtag('config', 'G-ABC123');"),
    ("analytics.web_counter", "host", "https://mc.yandex.ru/metrika/tag.js"),
    ("analytics.web_counter", "host", "https://www.googletagmanager.com/gtag/js?id=G-ABC123"),
    ("analytics.web_counter", "dom", '<script async src="https://mc.yandex.ru/metrika/tag.js"></script>'),
    ("analytics.session_replay", "manifest", '"@microsoft/clarity": "^1.0.0"'),
    ("analytics.session_replay", "code", "ym(1, 'init', { webvisor: true });"),
    ("analytics.session_replay", "host", "https://static.hotjar.com/c/hotjar-123.js"),
    ("analytics.session_replay", "dom", "<script>ym(1,'init',{webvisor:true})</script>"),
    ("ads.pixels", "code", '_tmr.push({ id: "3333333", type: "pageView" });'),
    ("ads.pixels", "host", "https://vk.com/rtrg?p=VK-RTRG-123-abc"),
    ("ads.pixels", "host", "https://top-fwz1.mail.ru/js/code.js"),
    ("ads.pixels", "dom", '<img src="https://top-fwz1.mail.ru/counter?id=3333333;js=na" alt="">'),
    ("ads.pixels_foreign", "manifest", '"react-facebook-pixel": "^1.0.4"'),
    ("ads.pixels_foreign", "code", "fbq('init', '123456789');"),
    ("ads.pixels_foreign", "code", "gtag('config', 'AW-1234567890');"),
    ("ads.pixels_foreign", "host", "https://connect.facebook.net/en_US/fbevents.js"),
    ("ads.pixels_foreign", "dom", '<img height="1" width="1" src="https://www.facebook.com/tr?id=1&ev=PageView">'),
    ("analytics.tag_manager", "manifest", '"react-gtm-module": "^2.0.11"'),
    ("analytics.tag_manager", "code", "const gtmId = 'GTM-ABC1234';"),
    ("analytics.tag_manager", "host", "https://www.googletagmanager.com/gtm.js?id=GTM-ABC1234"),
    ("analytics.tag_manager", "dom", '<iframe src="https://www.googletagmanager.com/ns.html?id=GTM-ABC1234"></iframe>'),
    ("analytics.mobile_sdk", "manifest", "  appmetrica_plugin: ^4.1.0\n"),
    ("analytics.mobile_sdk", "manifest", 'implementation("io.appmetrica.analytics:analytics:8.6.0")'),
    ("analytics.mobile_sdk", "code", "AppMetrica.activate(this, config)"),
    ("analytics.mobile_sdk", "host", "https://report.appmetrica.yandex.net/report"),
    # chat and communications
    ("chat.widget", "manifest", '"crisp-sdk-web": "^1.0.0"'),
    ("chat.widget", "code", "window.jivo_api.open();"),
    ("chat.widget", "host", "https://code.jivo.ru/widget/abc123"),
    ("chat.messenger_links", "manifest", '"react-floating-whatsapp": "^5.0.0"'),
    ("chat.messenger_links", "code", "const href = 'https://wa.me/79991234567';"),
    ("chat.messenger_links", "code", "const channel = 'https://t.me/shop_channel';"),
    ("chat.messenger_links", "dom", '<a href="https://wa.me/79991234567">WhatsApp</a>'),
    ("comms.email_marketing", "manifest", '"@mailchimp/mailchimp_marketing": "^3.0.0"'),
    ("comms.email_marketing", "code", "const client = require('unisender');"),
    ("comms.email_marketing", "host", "https://static.klaviyo.com/onsite/js/klaviyo.js"),
    ("comms.email_marketing", "dom", "<button>Подписаться на рассылку</button>"),
    ("comms.push", "manifest", "  firebase_messaging: ^15.0.0\n"),
    ("comms.push", "code", "Notification.requestPermission().then(cb);"),
    ("comms.push", "host", "https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.page.js"),
    ("comms.push", "dom", "<button>Включить уведомления</button>"),
    ("comms.sms", "manifest", '"twilio": "^5.0.0"'),
    ("comms.sms", "code", "send_sms(phone, text)"),
    ("comms.sms", "host", "https://sms.ru/sms/send?api_id=1"),
    ("comms.sms", "dom", "<p>СМС-уведомления о статусе заказа</p>"),
    ("comms.calls_calltracking", "code", "window.roistat = { visit: 1 };"),
    ("comms.calls_calltracking", "host", "https://mod.calltouch.ru/init.js?id=abc"),
    ("comms.calls_calltracking", "dom", '<div class="calltouch_phone">+7 495 000-00-00</div>'),
    # user content
    ("ugc.reviews", "manifest", '"react-star-ratings": "^2.3.0"'),
    ("ugc.reviews", "code", "<ReviewForm productId={id} />"),
    ("ugc.reviews", "host", "https://widget.trustpilot.com/bootstrap/v5/tp.widget.bootstrap.min.js"),
    ("ugc.reviews", "dom", "<button>Оставить отзыв</button>"),
    ("ugc.user_messaging", "manifest", '"stream-chat": "^8.0.0"'),
    ("ugc.user_messaging", "code", "class DirectMessage(models.Model):"),
    ("ugc.user_messaging", "dom", "<a>Личные сообщения</a>"),
    ("ugc.public_profiles", "code", "public_profile = models.BooleanField(default=True)"),
    ("ugc.public_profiles", "code", "app.get('/users/:username', handler)"),
    ("ugc.public_profiles", "dom", "<h2>Публичный профиль</h2>"),
    ("ugc.uploads", "manifest", '"react-dropzone": "^14.0.0"'),
    ("ugc.uploads", "code", "@UseInterceptors(FileInterceptor('file'))"),
    ("ugc.uploads", "host", "https://upload-widget.cloudinary.com/latest/global/all.js"),
    ("ugc.uploads", "dom", '<input type="file" name="avatar">'),
    ("ugc.image_uploads", "manifest", "  image_picker: ^1.1.0\n"),
    ("ugc.image_uploads", "code", "final picked = await picker.pickImage(source: ImageSource.gallery);"),
    ("ugc.image_uploads", "dom", '<input type="file" accept="image/*" name="avatar">'),
    ("content.webinars", "manifest", '"@zoom/meetingsdk": "^3.0.0"'),
    ("content.webinars", "code", "const webinar_id = 5;"),
    ("content.webinars", "host", "https://events.webinar.ru/12345/678"),
    ("content.webinars", "dom", "<a>Регистрация на вебинар</a>"),
    # audience
    ("audience.kids", "code", "parental_consent = True"),
    ("audience.kids", "dom", "<h1>Игры для детей 6-12 лет</h1>"),
    ("audience.adult_18", "code", "ageGate.show();"),
    ("audience.adult_18", "dom", "<button>Мне исполнилось 18 лет</button>"),
    # sectors (keyword evidence)
    ("sector.education_courses", "code", "course_enrollment = Enrollment()"),
    ("sector.education_courses", "host", "https://stepik.org/lesson/1"),
    ("sector.education_courses", "dom", "<h1>Онлайн-курсы по программированию</h1>"),
    ("sector.medical", "manifest", '"react-native-health": "^1.19.0"'),
    ("sector.medical", "code", "patient_id = request.GET['patient_id']"),
    ("sector.medical", "dom", "<a>Запись к врачу онлайн</a>"),
    ("sector.finance", "manifest", '"react-plaid-link": "^3.5.0"'),
    ("sector.finance", "code", "kyc_status = 'pending'"),
    ("sector.finance", "host", "https://cdn.plaid.com/link/v2/stable/link-initialize.js"),
    ("sector.finance", "dom", "<h1>Оформите микрозайм онлайн</h1>"),
    ("sector.gambling", "code", "class BetSlip:"),
    ("sector.gambling", "dom", "<h1>Онлайн казино и ставки на спорт</h1>"),
    ("sector.alcohol_tobacco", "code", "egais_id = order.egais_id"),
    ("sector.alcohol_tobacco", "dom", "<h1>Доставка пива и крепких напитков</h1>"),
    ("sector.gov", "code", "smev3_client = Smev3Client()"),
    ("sector.gov", "dom", "<h1>Портал государственных услуг</h1>"),
    ("sector.taxi_tourism", "manifest", '"amadeus": "^10.0.0"'),
    ("sector.taxi_tourism", "code", "pickup_location = ride.pickup"),
    ("sector.taxi_tourism", "host", "https://tp.media/content?promo_id=1"),
    ("sector.taxi_tourism", "dom", "<h1>Горящие путёвки и авиабилеты</h1>"),
    # technology
    ("tech.generative_ai", "manifest", '"openai": "^4.50.0"'),
    ("tech.generative_ai", "code", "client.messages.create(model='claude-sonnet-4-5', max_tokens=100)"),
    ("tech.generative_ai", "code", 'modelUri: "gpt://b1gxxxx/yandexgpt/latest",'),
    ("tech.generative_ai", "host", "https://api.openai.com/v1/chat/completions"),
    ("tech.generative_ai", "dom", "<p>Наш ИИ-ассистент ответит на вопросы</p>"),
    ("tech.generative_ai", "dom", "<button>Спросить ИИ</button>"),
    ("tech.generative_ai_foreign", "manifest", '"openai": "^4.50.0"'),
    ("tech.generative_ai_foreign", "code", "client.messages.create(model='claude-sonnet-4-5', max_tokens=100)"),
    ("tech.generative_ai_foreign", "host", "https://api.openai.com/v1/chat/completions"),
    ("tech.recommendations", "manifest", "implicit==0.7.2\n"),
    ("tech.recommendations", "code", "recs = recommendation_engine.recommend(user_id)"),
    ("tech.recommendations", "host", "https://cdn.retailrocket.ru/content/javascript/tracking.js"),
    ("tech.recommendations", "dom", "<h3>Персональные рекомендации фильмов</h3>"),
    # mobile
    ("mobile.app", "manifest", '"react-native": "0.76.0"'),
    ("mobile.app", "code", "import SwiftUI"),
    ("mobile.app", "host", "https://apps.apple.com/ru/app/id1234567890"),
    ("mobile.app", "dom", '<meta name="apple-itunes-app" content="app-id=1234567890">'),
    ("mobile.iap", "manifest", "  in_app_purchase: ^3.2.0\n"),
    ("mobile.iap", "code", "import StoreKit"),
    ("mobile.att", "manifest", "  app_tracking_transparency: ^2.0.6\n"),
    ("mobile.att", "code", "ATTrackingManager.requestTrackingAuthorization { status in }"),
    ("mobile.rustore", "manifest", 'implementation("ru.rustore.sdk:billingclient:6.0.0")'),
    ("mobile.rustore", "code", "import ru.rustore.sdk.billingclient.RuStoreBillingClient"),
    ("mobile.rustore", "host", "https://apps.rustore.ru/app/ru.example.app"),
    ("mobile.rustore", "dom", '<a href="https://apps.rustore.ru/app/ru.example.app">RuStore</a>'),
    # foreign resources
    ("foreign.fonts", "manifest", "  google_fonts: ^6.2.0\n"),
    ("foreign.fonts", "code", "final style = GoogleFonts.roboto();"),
    ("foreign.fonts", "host", "https://fonts.gstatic.com/s/inter/v13/inter.woff2"),
    ("foreign.fonts", "dom", '<link href="https://fonts.googleapis.com/css2?family=Inter" rel="stylesheet">'),
    ("foreign.captcha", "manifest", '"react-google-recaptcha": "^3.1.0"'),
    ("foreign.captcha", "code", "grecaptcha.ready(() => {});"),
    ("foreign.captcha", "host", "https://www.google.com/recaptcha/api.js"),
    ("foreign.captcha", "dom", '<div class="g-recaptcha" data-sitekey="x"></div>'),
    ("captcha.smartcaptcha", "code", "window.smartCaptcha.render(container, { sitekey });"),
    ("captcha.smartcaptcha", "host", "https://smartcaptcha.cloud.yandex.ru/captcha.js"),
    ("captcha.smartcaptcha", "dom", '<div class="smart-captcha" data-sitekey="x"></div>'),
    ("foreign.cdn_hosting", "manifest", '"@supabase/supabase-js": "^2.45.0"'),
    ("foreign.cdn_hosting", "code", "const url = 'https://abcdefgh.supabase.co';"),
    ("foreign.cdn_hosting", "host", "https://my-app.vercel.app/api/ping"),
    ("foreign.static_cdn", "code", "const src = 'https://code.jquery.com/jquery-3.7.1.min.js';"),
    ("foreign.static_cdn", "host", "https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css"),
    ("foreign.static_cdn", "dom", '<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>'),
    ("foreign.embeds", "manifest", '"react-youtube": "^10.1.0"'),
    ("foreign.embeds", "code", "new google.maps.Map(el, opts)"),
    ("foreign.embeds", "host", "https://maps.googleapis.com/maps/api/js?key=K"),
    ("foreign.embeds", "host", "https://docs.google.com/forms/d/e/abc/viewform"),
    ("foreign.embeds", "dom", '<iframe src="https://www.youtube.com/embed/abc123"></iframe>'),
    ("foreign.data_processors", "manifest", '"mixpanel-browser": "^2.50.0"'),
    ("foreign.data_processors", "manifest", "  firebase_analytics: ^11.0.0\n"),
    ("foreign.data_processors", "code", "const analytics = getAnalytics(app);"),
    ("foreign.data_processors", "host", "https://o123.ingest.sentry.io/api/1/envelope/"),
    ("foreign.data_processors", "code", "gtag('config', 'G-ABC123');"),
    ("foreign.data_processors", "host", "https://static.hotjar.com/c/hotjar-123.js"),
    ("foreign.data_processors", "host", "https://www.google-analytics.com/g/collect?v=2"),
    # advertising on the own resource, symbols, mentions, languages
    ("ads.own_site_promo", "code", 'erid: "2VtzqwP9nYf"'),
    ("ads.own_site_promo", "host", "https://yandex.ru/ads/system/context.js"),
    ("ads.own_site_promo", "dom", "<p>Реклама. ООО «Ромашка», ИНН 7700000000. erid: 2VtzqwP9nYf</p>"),
    ("ads.own_site_promo", "dom", '<a href="https://shop.example.ru/?erid=2Vtzqx1abc">Акция</a>'),
    ("content.meta_symbols", "manifest", '"react-instagram-embed": "^3.0.0"'),
    ("content.meta_symbols", "code", "import { FaInstagram } from 'react-icons/fa';"),
    ("content.meta_symbols", "host", "https://www.facebook.com/plugins/page.php?href=x"),
    ("content.meta_symbols", "dom", '<a href="https://www.instagram.com/shop/">Instagram</a>'),
    ("content.vpn_mentions", "code", "let manager = NEVPNManager.shared()"),
    ("content.vpn_mentions", "dom", "<a>Подключить VPN за 99 ₽ в месяц</a>"),
    ("content.vpn_mentions", "code", "image: teddysun/xray-core:latest"),
    ("i18n.foreign_language_ui", "code", "locales: ['ru', 'en'],"),
    ("i18n.foreign_language_ui", "code", "LANGUAGE_CODE = 'en-us'"),
    ("i18n.foreign_language_ui", "dom", '<html lang="en">'),
    ("i18n.foreign_language_ui", "dom", '<link rel="alternate" hreflang="de" href="/de">'),
]

# (signal kind, text, feature ids that must NOT match). Guards precision.
NEGATIVE_SAMPLES = [
    ("code", 'const { register } = useForm(); <input {...register("email")} />', {"forms.registration"}),
    ("code", "import { Inter } from 'next/font/google';", {"foreign.fonts"}),
    ("code", "import '@fontsource/inter';", {"foreign.fonts"}),
    ("code", "devServer: { proxy: { '/api': 'http://localhost:3000' } }", {"content.vpn_mentions"}),
    ("code", "const total = gym(3) + ymd(2);", {"analytics.web_counter", "analytics.session_replay"}),
    ("manifest", '"nodemailer": "^6.9.0"', {"comms.email_marketing", "comms.sms"}),
    ("manifest", '"react-native-web": "^0.19.0"', {"mobile.app"}),
    ("manifest", '"openai-compatible-fake": "^1.0.0"', set()),
    ("manifest", "django-simple-captcha==0.6\n", {"foreign.captcha"}),
    ("manifest", '"next": "15.0.0",\n"react": "19.0.0"', {"mobile.app", "payments.stripe"}),
    ("dom", '<footer><a href="/contacts">Контакты</a> Телефон: +7 (495) 000-00-00</footer>', {"forms.contact"}),
    ("dom", '<form action="/search"><input type="search" name="q"></form>', {"forms.contact", "forms.registration"}),
    ("dom", '<html lang="ru"><link rel="alternate" hreflang="ru" href="/">', {"i18n.foreign_language_ui"}),
    ("host", "https://fonts.example.ru/inter.woff2", {"foreign.fonts"}),
    ("host", "https://notvercel.app/x", {"foreign.cdn_hosting"}),
    ("host", "https://www.example.ru/page", set()),
    # regressions found when scanning real projects
    ("code", "track('signup'); const stage = 'register';", {"forms.registration"}),
    ("code", "const born = user.birthdate; const dob = tg.birthdate;", {"audience.kids"}),
    ("dom", "<p>Родительский элемент и родители страницы</p>", {"audience.kids"}),
    ("dom", "<p>Оплата банковской или кредитной картой. Займёмся вашим вопросом.</p>", {"sector.finance"}),
    ("code", "await supabase.auth.mfa.enroll({ factorType: 'totp' })", {"sector.education_courses"}),
    ("code", "const conversationId = chat.conversation_id;", {"ugc.user_messaging"}),
    ("code", "prescription = plan.prescription", {"sector.medical"}),
    ("code", "dice = Emoji.SLOT_MACHINE; label = 'slot_machine'", {"sector.gambling"}),
    ("code", "doc.type = 'driver_license'", {"sector.taxi_tourism"}),
    ("host", "https://accounts.google.com/o/oauth2/auth", {"auth.google"}),
    ("dom", "<p>Скидка на 18 + 5 товаров</p>", {"audience.adult_18"}),
    ("dom", "<p>Вину признаю, пивоварня не при чём</p>", {"sector.alcohol_tobacco"}),
    ("dom", "<script>if (mode === 'signup') { import crypto from 'crypto'; }</script>", {"forms.registration", "sector.finance"}),
    ("code", "// improves customer loyalty and retention", {"commerce.loyalty_points"}),
    ("code", "if (chat.type === 'private message') return;", {"ugc.user_messaging"}),
    ("dom", '<script src="https://connect.facebook.net/en_US/fbevents.js"></script>', {"content.meta_symbols"}),
    # fix round 1: precision of the review
    ("code", "bot.send_message(chat_id, text, message_thread_id=topic_id)", {"ugc.user_messaging"}),
    ("code", "xray_image = load_dicom(path)  # chest x-ray, hysteria score", {"content.vpn_mentions"}),
    ("dom", "<p>Для доступа к корпоративной сети сотрудники используют VPN</p>", {"content.vpn_mentions"}),
    ("dom", "<p>Сайт работает через VPN</p>", {"content.vpn_mentions"}),
    ("dom", "<p>Как нейросети меняют рынок труда: ChatGPT и его аналоги</p>", {"tech.generative_ai"}),
    ("code", "layer = nn.LSTM(64)  # recurrent layer", {"commerce.subscription"}),
    ("code", "save_payment_method: true, setup_future_usage: 'off_session'", {"commerce.subscription"}),
    ("code", "const { addToCart } = useCart();", {"commerce.cart_physical"}),
    ("dom", "<button>В корзину</button>", {"commerce.cart_physical"}),
    ("code", "languages: ['en', 'python', 'go'],", {"i18n.foreign_language_ui"}),
    ("code", "sbp = vitals.sbp; dbp = vitals.dbp", {"payments.sbp"}),
    ("dom", "<footer>Сетевое издание «Пример». 18+</footer>", {"audience.adult_18"}),
    ("dom", '<a href="https://t.me/shop_channel">Наш канал в Telegram</a>', {"chat.widget", "auth.telegram"}),
    ("host", "https://code.jquery.com/jquery-3.7.1.min.js", {"foreign.cdn_hosting", "foreign.data_processors"}),
    ("code", "fbq('init', '1');", {"ads.pixels"}),
    ("code", "ym(12345678, 'init', { clickmap: true });", {"foreign.data_processors"}),
    ("dom", "<p>Кондиционеры: сплит-системы в рассрочку от банка-партнёра</p>", {"payments.bnpl"}),
    ("dom", "<p>Акции и скидки недели</p>", {"marketing.giveaways"}),
    ("dom", "<h3>Популярные товары</h3>", {"tech.recommendations"}),
    # fix round 2
    ("dom", "<p>Мы создаём сайты с помощью нейросетей</p>", {"tech.generative_ai"}),
    ("dom", "<p>Сервис работает на базе нейросети</p>", {"tech.generative_ai"}),
    ("dom", "<p>AI-powered analytics for your shop</p>", {"tech.generative_ai"}),
    ("dom", "<p>Рекомендуем вам ознакомиться с правилами</p>", {"tech.recommendations"}),
    ("dom", "<h3>Вам может понравиться</h3>", {"tech.recommendations"}),
    ("dom", "<p>Скачайте ВПН-клиент для доступа к офису</p>", {"content.vpn_mentions"}),
    ("dom", "<p>Рассрочка от 1 990 ₽ в месяц</p>", {"commerce.subscription"}),
    ("manifest", '"@sentry/react": "^8.0.0"', {"foreign.data_processors"}),
    ("code", "Sentry.init({ dsn: SENTRY_DSN });", {"foreign.data_processors"}),
    ("code", "giga = GigaChat(credentials=KEY)", {"tech.generative_ai_foreign"}),
    ("host", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions", {"tech.generative_ai_foreign"}),
    ("dom", '<input type="file" name="resume" accept=".pdf">', {"ugc.image_uploads"}),
    ("dom", '<form action="/search" method="get"><input name="q"></form>', {"forms.generic"}),
    ("dom", "<p>Консультации дизайнера интерьера</p>", {"sector.medical"}),
]


# ----------------------------------------------------------------- the tests

def test_catalog_is_a_json_list():
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data, "catalog.json must be a non-empty JSON array"


def test_entry_shape():
    problems = []
    for entry in load_catalog():
        keys = set(entry)
        missing = set(REQUIRED_KEYS) - keys
        extra = keys - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS)
        if missing or extra:
            problems.append(f"{entry.get('id')}: missing={sorted(missing)} extra={sorted(extra)}")
            continue
        for key in ("id", "title_ru", "title_en"):
            if not isinstance(entry[key], str) or not entry[key].strip():
                problems.append(f"{entry['id']}: {key} must be a non-empty string")
        for key in (*SIGNAL_KEYS, "stacks"):
            value = entry[key]
            if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
                problems.append(f"{entry['id']}: {key} must be a list of non-empty strings")
            elif len(set(value)) != len(value):
                problems.append(f"{entry['id']}: duplicates in {key}")
        if "notes" in entry and not (isinstance(entry["notes"], str) and entry["notes"].strip()):
            problems.append(f"{entry['id']}: notes must be a non-empty string")
    assert not problems, "\n".join(problems)


def test_ids_are_unique_and_well_formed():
    ids = [e["id"] for e in load_catalog()]
    assert len(ids) == len(set(ids)), "duplicate ids"
    bad = [i for i in ids if not ID_RE.match(i)]
    assert not bad, f"ids not matching {ID_RE.pattern}: {bad}"


def test_brief_ids_are_present():
    ids = {e["id"] for e in load_catalog()}
    assert not (set(EXPECTED_IDS) - ids), f"missing: {sorted(set(EXPECTED_IDS) - ids)}"


def test_every_entry_has_a_signal():
    empty = [e["id"] for e in load_catalog() if not any(e[k] for k in SIGNAL_KEYS)]
    assert not empty, f"entries without any signal: {empty}"


def test_titles():
    problems = []
    for e in load_catalog():
        if not CYRILLIC_RE.search(e["title_ru"]):
            problems.append(f"{e['id']}: title_ru has no Cyrillic")
        if CYRILLIC_RE.search(e["title_en"]):
            problems.append(f"{e['id']}: title_en contains Cyrillic")
    assert not problems, "\n".join(problems)


def test_stacks_values():
    problems = []
    for e in load_catalog():
        stacks = e["stacks"]
        if not stacks:
            problems.append(f"{e['id']}: empty stacks")
        elif "*" in stacks and len(stacks) > 1:
            problems.append(f"{e['id']}: '*' must stand alone")
        unknown = [s for s in stacks if s != "*" and s not in STACKS]
        if unknown:
            problems.append(f"{e['id']}: unknown stacks {unknown}")
    assert not problems, "\n".join(problems)


def test_regexes_compile_cleanly():
    problems = []
    for e in load_catalog():
        for key in ("code", "dom"):
            for pattern in e[key]:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error")  # flags not at the start are an error
                        rx = re.compile(pattern)
                except (re.error, DeprecationWarning, FutureWarning) as exc:
                    problems.append(f"{e['id']}.{key}: {pattern!r}: {exc}")
                    continue
                if len(pattern) > 800:
                    problems.append(f"{e['id']}.{key}: pattern longer than 800 chars: {pattern[:60]!r}")
                if rx.search("") or rx.search(" \n\t"):
                    problems.append(f"{e['id']}.{key}: matches empty/blank text: {pattern!r}")
                if "(?>" in pattern or "(?P<" in pattern:
                    problems.append(f"{e['id']}.{key}: atomic or named group not allowed: {pattern!r}")
    assert not problems, "\n".join(problems)


def test_regexes_are_not_catastrophic():
    adversarial = [
        "<form " * 400,
        "a" * 30000,
        " " * 30000,
        '"' * 6000,
        '<input type="password" ' * 300,
        "<iframe src=\"" * 300,
        "ym(" * 3000,
        "<script " * 3000,
        "<img " * 3000,
        "<a " * 3000,
        "<link " * 3000,
        "1 " * 15000,
        "[" * 5000,
        "class=\"" * 3000,
    ]
    slow = []
    for e in load_catalog():
        for key in ("code", "dom"):
            for pattern in e[key]:
                rx = re.compile(pattern)
                for text in adversarial:
                    started = time.perf_counter()
                    rx.search(text)
                    elapsed = time.perf_counter() - started
                    if elapsed > 1.0:
                        slow.append(f"{e['id']}.{key}: {elapsed:.1f}s on {text[:12]!r}: {pattern[:70]!r}")
    assert not slow, "\n".join(slow)


def test_hosts_and_deps_look_right():
    problems = []
    for e in load_catalog():
        for host in e["hosts"]:
            if not HOST_RE.match(host) or "." not in host.split("/")[0]:
                problems.append(f"{e['id']}: bad host {host!r} (lowercase host[/path], no scheme)")
        for dep in e["deps"]:
            if re.search(r"\s|[\"']|://", dep):
                problems.append(f"{e['id']}: bad dep {dep!r}")
    assert not problems, "\n".join(problems)


def test_no_legal_content_or_private_paths():
    raw = CATALOG_PATH.read_text(encoding="utf-8")
    for pattern in PRIVACY_PATTERNS:
        assert pattern not in raw, f"private-looking text in catalog: {pattern!r}"
    problems = []
    for e in load_catalog():
        prose = " ".join([e["title_ru"], e["title_en"], e.get("notes", "")])
        if LEGAL_RE.search(prose):
            problems.append(f"{e['id']}: legal citation in titles/notes")
        if YEAR_RE.search(prose):
            problems.append(f"{e['id']}: year/date in titles/notes")
    for number in re.findall(r"\b\d{2,3}-ФЗ\b|\bст\.\s*\d+", raw):
        problems.append(f"legal citation {number!r} in catalog")
    assert not problems, "\n".join(problems)


def test_keyword_features_are_marked_weak():
    problems = []
    for e in load_catalog():
        if e["id"].startswith(WEAK_PREFIXES) or e["id"] in WEAK_IDS:
            notes = e.get("notes", "").lower()
            if "weak" not in notes or "owner" not in notes:
                problems.append(f"{e['id']}: notes must say the evidence is weak and the owner must confirm")
    assert not problems, "\n".join(problems)


def test_unverified_names_are_flagged():
    # Entries whose package names could not be confirmed carry a "verify" note.
    flagged = [e["id"] for e in load_catalog() if "verify" in e.get("notes", "").lower()]
    assert flagged, "expected at least one entry with a 'verify' note"


@pytest.mark.parametrize(
    "feature,kind,text",
    POSITIVE_SAMPLES,
    ids=[f"{f}-{k}-{i}" for i, (f, k, _) in enumerate(POSITIVE_SAMPLES)],
)
def test_positive_sample_matches(feature, kind, text):
    assert feature in MATCHERS[kind](text), f"{feature} did not match its {kind} sample: {text!r}"


def test_every_signal_group_has_a_positive_sample():
    covered = {(f, k) for f, k, _ in POSITIVE_SAMPLES}
    missing = []
    for e in load_catalog():
        for group, kind in GROUP_TO_KIND.items():
            if e[group] and (e["id"], kind) not in covered:
                missing.append(f"{e['id']}.{group}")
    assert not missing, f"signal groups without a positive sample: {missing}"


@pytest.mark.parametrize("kind,text,forbidden", NEGATIVE_SAMPLES,
                         ids=[f"neg-{i}" for i in range(len(NEGATIVE_SAMPLES))])
def test_negative_sample_stays_quiet(kind, text, forbidden):
    found = MATCHERS[kind](text)
    assert not (found & forbidden), f"false positive {sorted(found & forbidden)} on {text!r}"
    if not forbidden:
        assert not found, f"unexpected match {sorted(found)} on {text!r}"


FIXTURE_CASES = [
    ("nextjs/app/layout.tsx", {"analytics.web_counter", "analytics.session_replay"},
     {"foreign.fonts", "i18n.foreign_language_ui", "forms.contact"}),
    ("nextjs/package.json", {"auth.vk_id", "payments.yookassa", "payments.stripe", "tech.generative_ai"},
     {"mobile.app", "payments.paddle"}),
    ("flutter/pubspec.yaml",
     {"mobile.app", "analytics.mobile_sdk", "foreign.fonts", "mobile.iap", "mobile.att", "comms.push"},
     {"payments.stripe"}),
    ("ios/App.swift", {"mobile.app", "mobile.iap", "mobile.att", "auth.apple", "analytics.mobile_sdk"}, set()),
    ("django/requirements.txt",
     {"payments.yookassa", "tech.generative_ai", "payments.stripe", "forms.registration", "foreign.captcha"},
     {"payments.paddle"}),
    ("django/templates/base.html", {"foreign.fonts", "foreign.captcha", "forms.contact"},
     {"captcha.smartcaptcha"}),
    ("static/index.html",
     {"payments.cloudpayments", "chat.widget", "ads.pixels", "ads.pixels_foreign", "foreign.data_processors",
      "ads.own_site_promo", "foreign.embeds"},
     {"payments.stripe", "content.meta_symbols"}),
]


@pytest.mark.parametrize("name,expected,forbidden", FIXTURE_CASES, ids=[c[0] for c in FIXTURE_CASES])
def test_fixture_detection(name, expected, forbidden):
    found = detect_file(FIXTURES / name)
    assert expected <= found, f"{name}: not detected {sorted(expected - found)}; found {sorted(found)}"
    assert not (forbidden & found), f"{name}: false positives {sorted(forbidden & found)}"


def test_clean_page_matches_nothing():
    found = detect_file(FIXTURES / "static" / "clean.html")
    assert not found, f"clean page triggered {sorted(found)}"
