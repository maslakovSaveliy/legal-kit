# Python web (Django, Flask, FastAPI)

Mechanics for editing an existing server-rendered Python project. Django is covered in detail; Flask and FastAPI differences are called out inline. The knowledge pack decides which forms need consent and which texts to show; this file shows the mechanics. Reuse the project's base template, CSS framework and translation setup. Add no frontend library.

Contents: [Detect](#detect) | [Legal pages](#legal-pages) | [Consent checkbox in forms](#consent-checkbox-in-forms) | [Analytics gated by consent](#analytics-gated-by-consent) | [Consent banner](#consent-banner) | [Consent log](#consent-log-existing-backend-only) | [Footer and links](#footer-and-links) | [i18n](#i18n) | [Verify and record state](#verify-and-record-state)

## Detect
- Django: `manage.py`, `<project>/settings.py` (or `settings/`), `INSTALLED_APPS`, `urls.py`, `templates/`, `base.html`. Flask: `Flask(__name__)`, `templates/`, blueprints. FastAPI: `FastAPI()`, `Jinja2Templates`, or API only (then the frontend stack file covers pages; this file covers the endpoint and enforcement).
- ORM (decides whether a consent log is allowed): Django ORM (`models.py`, `migrations/`), SQLAlchemy/SQLModel (`alembic.ini`, `alembic/versions`), Tortoise, Peewee. None: no consent log.
- Forms: Django `forms.Form`/`ModelForm` (+ `crispy_forms`, `django-widget-tweaks`), Flask-WTF/WTForms (`FlaskForm`), Pydantic request models (FastAPI), HTMX (`hx-post`).
- CSS/UI: Bootstrap, Tailwind (`django-tailwind`, `tailwind.config.js`), Bulma, a custom `static/css`. Reuse its classes and tokens (CSS variables).
- Analytics today: `grep -rnE "mc.yandex.ru|ym\(|googletagmanager|gtag|connect.facebook.net|vk.com/rtrg" templates static`. Usually in `base.html`.
- i18n: Django `locale/<lang>/LC_MESSAGES/django.po` + `LocaleMiddleware` + `{% load i18n %}`; Flask-Babel (`babel.cfg`, `translations/`); none.
- Package files: `pyproject.toml`, `requirements*.txt`, `Pipfile`; virtualenv in `.venv`/`venv`.

## Legal pages
- Existing route takes priority: search first (`grep -rniE "privacy|policy|oferta|offer|terms" --include=urls.py --include=*.html .`, menus, sitemap) and update that page; never create a duplicate policy page. Only when none exists use `/legal/{privacy,offer,refund,requisites}` (slugs from the documents step).
- Django: one `TemplateView` per document, templates extend `base.html`. Reuse existing content-page wrappers (`{% block content %}`, container classes).
```python
# urls.py
from django.views.generic import TemplateView
urlpatterns += [
    path("legal/privacy/", TemplateView.as_view(template_name="legal/privacy.html"), name="legal-privacy"),
    # offer, refund, requisites: slugs from the documents step
]
```
- Templates under `templates/legal/<slug>.html`: `{% extends "base.html" %}{% load i18n %}`, the document HTML inside a `{% block content %}`. Convert the Markdown from the documents step to plain HTML by hand or with a one-off script; do not add a Markdown package. If `django.contrib.flatpages` is already installed, use it instead.
- Flask: `@app.get("/legal/<slug>")` rendering `legal/{slug}.html`, only for slugs in a fixed allowlist (never build a template path from the raw parameter). FastAPI with Jinja2: the same via `TemplateResponse`.
- Add the URLs to the project's sitemap (`django.contrib.sitemaps`) if one exists. Do not add `noindex`.
- Check login-required middleware and `LOGIN_REQUIRED` mixins do not cover `/legal/`.

## Consent checkbox in forms
- Unchecked by default, a field of its own, separate from "accept the offer/terms". Label from gettext; the policy link opens in a new tab and sits outside the `<label>` click area.
- Submit stays enabled unless the knowledge pack says consent is required for that form. Django `BooleanField(required=True)` already rejects an unchecked box on the server, which is the real enforcement:
```python
class LeadForm(forms.Form):
    # ...existing fields
    consent_pd = forms.BooleanField(
        required=True,            # False when this form does not need consent
        initial=False,
        label=_("consent.pd.label"),   # text from the documents step, via the catalog
        error_messages={"required": _("consent.pd.required")},
    )
```
- Template: render `{{ form.consent_pd }}` with the project's form helper (crispy `|as_crispy_field`, widget-tweaks classes). When required, add the `required` attribute and, optionally, a button disabled until checked:
```html
<button type="submit" id="submit" disabled>{% translate "Submit" %}</button>
<script>document.getElementById('id_consent_pd').addEventListener('change',
  function (e) { document.getElementById('submit').disabled = !e.target.checked; });</script>
```
  Remove `disabled` and the script for forms that do not require consent.
- Flask-WTF: `BooleanField(label, validators=[DataRequired()])` (required) or `BooleanField(label)`. Pydantic: `consent_pd: Literal[True]` (required) or `bool = False`.
- After a successful save, write the consent log row with this form's `form_id`, in the same view/transaction.

## Analytics gated by consent
- Remove the inline counter snippets and `<noscript><img src="https://mc.yandex.ru/watch/...">` pixels from `base.html`; no server-side event should fire before consent either.
- Use the plain-JS loader and banner from `static-html.md` (`consent.js`): copy it to `static/legal/consent.js`, load it with `<script src="{% static 'legal/consent.js' %}" defer data-ym="{{ YM_COUNTER_ID }}" data-log="{% url 'record-consent' %}" data-csrf-header="X-CSRFToken" data-csrf-token="{{ csrf_token }}"></script>` at the end of `base.html` (drop the `data-log` and `data-csrf-*` attributes when there is no consent log), and pass the counter IDs from settings via a context processor. The JS loads Metrica/GA/pixels only after the stored choice allows it, so full-page caching stays safe.
- Revoke path: the "Cookie settings" footer link described in `static-html.md`.
- Do not set analytics cookies from middleware or views. Django's own session/CSRF cookies are not part of this change.

## Consent banner
Markup and script come from `static-html.md`. Put the banner partial in `templates/legal/_consent_banner.html` and `{% include %}` it in `base.html`, using the project's CSS framework classes (Bootstrap alert/toast, Tailwind utility classes) and tokens. Texts via `{% translate %}`; pass them to JS as `data-` attributes on the banner element so the catalog stays the single source. Bumping `data-version` invalidates the stored choice and reopens the banner. Accept all and Reject get the same button class and size; Accept all sets `analytics` and `marketing`, Reject sets neither, and the Settings view has two separate toggles, unchecked by default.

## Consent log (existing backend only)
Only with an existing database and ORM from Detect. NEVER introduce a new database, ORM or migration tool. Append-only: no update or delete code path, no admin edit.
Log payload (identical in every stack file): `{ subjectId, consentVersion, formId, channel, action }`; `action` is `grant` or `revoke`, `channel` is `web`, `ios` or `android`. The request keys are camelCase; the columns below are snake_case and the view maps one to the other. Log only `grant` and `revoke` (revoke = withdrawing a previously granted category); a first-time refusal is not logged: no consent was given, so there is nothing to prove and the row would only add personal data.
The log itself holds personal data (`subjectId`, `ip`, `userAgent`): list it among the processing described in the privacy policy (documents step), restrict read access, apply the retention period given by the documents step, and never store form contents in it.
Place the model in an existing app that fits, or create one: `python manage.py startapp legal`, add `"legal"` to `INSTALLED_APPS`, then `makemigrations legal` (it does not apply anything). Without an installed Django, write `legal/migrations/__init__.py` and `0001_initial.py` (`migrations.CreateModel` with the same fields and `options={"db_table": "consent_log"}`) by hand and leave `makemigrations --check` to the owner.
```python
# legal/models.py (Django, USE_TZ = True stores UTC)
class ConsentLog(models.Model):
    class Action(models.TextChoices):
        GRANT = "grant"
        REVOKE = "revoke"
    subject_id = models.CharField(max_length=128, db_index=True)   # user id, else anonymous UUID from the client
    created_at = models.DateTimeField(auto_now_add=True)
    consent_version = models.CharField(max_length=32)
    text_sha256 = models.CharField(max_length=64)
    channel = models.CharField(max_length=8, choices=[("web", "web"), ("ios", "ios"), ("android", "android")])
    form_id = models.CharField(max_length=64)
    ip = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True)
    action = models.CharField(max_length=6, choices=Action.choices)

    class Meta:
        db_table = "consent_log"   # the same table name in every stack

    def save(self, *args, **kwargs):
        if self.pk: raise RuntimeError("consent log is append-only")
        super().save(*args, **kwargs)
    def delete(self, *args, **kwargs): raise RuntimeError("consent log is append-only")
```
```python
# legal/consent_texts.py: the exact text shown to the user, per version (from the documents step; bump the key with data-version)
CONSENT_TEXTS = {"1": "[consent text, RU authoritative, exactly as rendered]"}

# legal/forms.py
from django import forms

class ConsentEventForm(forms.Form):          # keys are exactly what consent.js sends
    subjectId = forms.CharField(max_length=128)
    consentVersion = forms.CharField(max_length=32)
    formId = forms.CharField(max_length=64)
    channel = forms.ChoiceField(choices=[("web", "web"), ("ios", "ios"), ("android", "android")])
    action = forms.ChoiceField(choices=[("grant", "grant"), ("revoke", "revoke")])

# legal/views.py
import hashlib
import json

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_POST

from .consent_texts import CONSENT_TEXTS
from .forms import ConsentEventForm
from .models import ConsentLog


@require_POST   # CSRF stays on: consent.js sends the token in the X-CSRFToken header
def record_consent(request):
    try:
        payload = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    form = ConsentEventForm(payload if isinstance(payload, dict) else {})
    if not form.is_valid() or form.cleaned_data["consentVersion"] not in CONSENT_TEXTS:
        return HttpResponseBadRequest()
    cd = form.cleaned_data
    text = CONSENT_TEXTS[cd["consentVersion"]]
    ConsentLog.objects.create(
        subject_id=cd["subjectId"], consent_version=cd["consentVersion"], form_id=cd["formId"],
        channel=cd["channel"], action=cd["action"], ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", ""), text_sha256=hashlib.sha256(text.encode()).hexdigest())
    return HttpResponse(status=204)

# legal/urls.py (included from the project urls): path("legal/consent/", record_consent, name="record-consent")
```
- Compute the hash server-side from the known text of that version; never trust a client hash. For logged-in users take the subject from `request.user.pk`, not from the body.
- `REMOTE_ADDR` is the real client only when the proxy is configured (nginx `real_ip`, gunicorn `forwarded_allow_ips`); do not read `X-Forwarded-For` unless the deployment guarantees it.
- Register the model in `admin.py` read-only (`has_add/change/delete_permission` return False). QuerySet `update()`/`delete()` bypass `save()`; for a hard guarantee ask the owner about DB-level privileges.
- SQLAlchemy: same columns on a `DeclarativeBase` model with `__tablename__ = "consent_log"`, insert-only helper; `alembic revision --autogenerate -m "add consent_log"` only when the database host in the configuration is `localhost`, `127.0.0.1`, `::1` or a local socket, otherwise write the revision by hand or leave the command in «Сделать вам» ([ui-integration.md](../workflow/ui-integration.md#consent-log)). FastAPI/Flask: the same handler shape with the framework's request object.

## Footer and links
Add Политика / Оферта / Возврат / Реквизиты to the footer block of `base.html` (or the `footer.html` partial), with `{% url 'legal-privacy' %}` etc. and `{% translate %}` labels; also next to each consent checkbox and in the banner. Add the "Cookie settings" link there. If a copyright line exists, extend it only to the short footer form of the owner's status (name, OGRN or OGRNIP where section 3.2 prints it, address, e-mail; INN only for a self-employed owner) from `.legal/answers.json`; never invent values. The owner details the footer shows (which requisites, by the owner's status) follow [ui-integration.md](../workflow/ui-integration.md#footer-and-requisites).

## i18n
- Django: wrap strings in `{% translate %}` / `gettext_lazy`, add entries with `python manage.py makemessages -l ru -l en`, fill the `.po` files, then `python manage.py compilemessages`. Check `LOCALE_PATHS` and `LANGUAGES` in settings.
- Flask-Babel: `_()` and `pybabel extract/update/compile`.
- RU strings and documents are authoritative. EN versions are translations: add a `translation.notice` message and render it at the top of every EN legal template.
- No i18n in the project: keep text in the templates in one language plus a constants module; do not enable i18n machinery.

## Verify and record state
- Django: `python manage.py check`; after adding the model run `python manage.py makemigrations legal`, then `python manage.py makemigrations --check --dry-run` must report no changes (never run `migrate`; put it in «Сделать вам»); `python manage.py test`. Add tests that post the exact payload `consent.js` sends, so a key mismatch fails here:
```python
class ConsentEndpointTests(TestCase):
    PAYLOAD = {"subjectId": "t1", "consentVersion": "1", "formId": "cookie-banner", "channel": "web", "action": "grant"}
    def post(self, body):
        return self.client.post(reverse("record-consent"), body, content_type="application/json")
    def test_records_a_row(self):
        self.assertEqual(self.post(json.dumps(self.PAYLOAD)).status_code, 204)
        self.assertEqual(ConsentLog.objects.count(), 1)
    def test_rejects_unknown_version_and_bad_json(self):
        self.assertEqual(self.post(json.dumps({**self.PAYLOAD, "consentVersion": "nope"})).status_code, 400)
        self.assertEqual(self.post("{not json").status_code, 400)
    def test_existing_row_cannot_be_saved_again(self):
        self.post(json.dumps(self.PAYLOAD))
        with self.assertRaises(RuntimeError):
            ConsentLog.objects.get().save()
```
- Other: `ruff check .`, `mypy .`, `pytest` when configured. Never `alembic upgrade head` or another migration command that applies.
- Search check: counter hosts appear only in `consent.js`. Run the server and load a page with empty cookies: no request to counter hosts before Accept.
- Record every created or edited file in `.legal/state.json` `managed[]` (`path`, `sha256` of the final content, `kind`: `page` | `checkbox` | `banner` | `footer` | `consent-log`). Do not commit.
