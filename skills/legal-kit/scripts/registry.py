#!/usr/bin/env python3
"""Look up a public Russian registry. Python 3.9+, standard library only (urllib, socket).

    registry.py egrul|npd|whois|cbr|rkn ARG [--date YYYY-MM-DD]

egrul: INN/OGRN/OGRNIP at egrul.nalog.ru (the JSON flow described in registries.md).
npd:   12-digit INN and a date at statusnpd.nalog.ru (at most 2 requests per minute per IP; when the
       service says so, the answer is `manual`: wait a minute or check by hand).
whois: domain at whois.tcinet.ru:43 (punycode for .rf).
cbr:   OGRN at cbr.ru/finorg (minimal parsing, otherwise `manual`).
rkn:   INN; the operators registry is never scraped, the answer is always `manual`.

Prints {status: ok|not_found|manual|error, data, url, checked_at[, note]}. A captcha, HTTP 403/429
or a timeout, or an HTML page where JSON was expected, gives `manual` with the address and what the
user should paste back; a captcha is never solved or bypassed. With LEGAL_KIT_OFFLINE=1 the answer is read from
$LEGAL_KIT_STUBS/<kind>-<arg>.json and the network is not touched.

Exit codes: 0 ok / not_found / manual, 1 error, 2 bad input.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _kb  # noqa: E402  (must come first: it protects the stdlib `select` module)

import argparse  # noqa: E402
import encodings.idna  # noqa: E402,F401  (punycode for .rf domains)
import json  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402

USER_AGENT = "legal-kit-registry/0.1"
TIMEOUT = 15
MAX_BODY = 2 * 1024 * 1024
EGRUL_URL = "https://egrul.nalog.ru/"
NPD_API = "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status"
NPD_URL = "https://npd.nalog.ru/check-status/"
WHOIS_HOST = "whois.tcinet.ru"
WHOIS_URL = WHOIS_HOST + ":43"
CBR_URL = "https://www.cbr.ru/finorg/foinfo/?ogrn=%s"
RKN_URL = "https://pd.rkn.gov.ru/operators-registry/operators-list/"
NPD_LIMIT_CODE = "taxpayer.status.service.limited.error"
NPD_UNAVAILABLE_CODE = "taxpayer.status.service.unavailable.error"
WHOIS_KEYS = ("domain", "state", "org", "registrar", "created", "paid-till", "free-date", "taxpayer-id",
              "admin-contact")
STATUSES = ("ok", "not_found", "manual", "error")

def pause(seconds):
    time.sleep(seconds)


class Blocked(Exception):
    """Captcha, 403/429, geo block or timeout: the user has to check by hand."""


class HttpFailure(Exception):
    def __init__(self, code, body):
        super().__init__("HTTP %s" % code)
        self.code = code
        self.body = body


class NetworkFailure(Exception):
    pass


def answer(status, url, data=None, note=None, **extra):
    result = {"status": status, "data": data if data is not None else {}, "url": url, "checked_at": _kb.utc_now()}
    if note:
        result["note"] = note
    result.update(extra)
    return result


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def check_inn(arg, lengths=(10, 12)):
    if len(arg) not in lengths or not _kb.inn_valid(arg):
        raise _kb.KbError("%r is not a valid INN (digits, correct check digit, length %s)"
                          % (arg, " or ".join(map(str, lengths))))
    return arg


def check_ogrn(arg):
    if not _kb.ogrn_valid(arg):
        raise _kb.KbError("%r is not a valid OGRN/OGRNIP (13 or 15 digits with a correct check digit)" % arg)
    return arg


def validate(kind, arg):
    """Normalised key for the registry, or KbError."""
    arg = arg.strip()
    if kind == "egrul":
        return check_ogrn(arg) if len(arg) in (13, 15) else check_inn(arg)
    if kind == "npd":
        return check_inn(arg, (12,))
    if kind == "cbr":
        return check_ogrn(arg)
    if kind == "rkn":
        return check_inn(arg)
    domain = arg.lower().rstrip(".")
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError:
        raise _kb.KbError("%r is not a valid domain name" % arg)
    if not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", ascii_domain) or len(ascii_domain) > 253:
        raise _kb.KbError("%r is not a valid domain name" % arg)
    return ascii_domain


# --------------------------------------------------------------------------
# Offline stubs
# --------------------------------------------------------------------------

def offline():
    return os.environ.get("LEGAL_KIT_OFFLINE", "").strip().lower() in ("1", "true", "yes")


def stub_answer(kind, names):
    folder = os.environ.get("LEGAL_KIT_STUBS")
    if not folder:
        return None
    for name in names:
        path = os.path.join(folder, "%s-%s.json" % (kind, name))
        if os.path.isfile(path):
            try:
                stub = _kb.load_json(path)
            except _kb.KbError as exc:
                return answer("error", "", note=str(exc))
            if not isinstance(stub, dict) or stub.get("status") not in STATUSES:
                return answer("error", "", note="stub %s has no valid status" % path)
            result = {key: value for key, value in stub.items() if not key.startswith("_")}
            result.setdefault("data", {})
            result.setdefault("url", "")
            result.setdefault("checked_at", _kb.utc_now())
            result["offline"] = True
            return result
    return None


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------

def http(method, url, data=None, headers=None):
    """(status, body bytes). Raises Blocked, HttpFailure or NetworkFailure."""
    request = urllib.request.Request(url, data=data, method=method,
                                     headers=dict({"User-Agent": USER_AGENT}, **(headers or {})))
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return getattr(response, "status", 200), response.read(MAX_BODY)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(MAX_BODY)
        except Exception:  # noqa: BLE001 - the body of an error page is optional
            body = b""
        if exc.code in (401, 403, 429):
            raise Blocked("HTTP %s" % exc.code)
        raise HttpFailure(exc.code, body)
    except (socket.timeout, TimeoutError):
        raise Blocked("timeout")
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise Blocked("timeout")
        raise NetworkFailure(str(exc.reason))
    except OSError as exc:
        raise NetworkFailure(str(exc))


def json_body(body):
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def looks_like_captcha(body):
    return b"captcha" in body.lower() or "капч".encode("utf-8") in body.lower()


WAIT_HINT_RU = "Подождите минуту и повторите / проверьте вручную по ссылке: %s"


def looks_like_html(body):
    return body.lstrip()[:1] == b"<"


def manual(kind, arg, reason, url=None, wait_hint=False):
    """status manual: say where to look and what to paste back."""
    where = url or {"egrul": EGRUL_URL, "npd": NPD_URL, "cbr": CBR_URL % arg, "rkn": RKN_URL}.get(kind, "")
    pastes = {
        "egrul": "the name, OGRN or OGRNIP, address or region and the status (active or terminated), or attach the extract",
        "npd": "the service answer (is the INN a payer of the professional income tax on that date)",
        "whois": "the registrar, creation date and paid-till date from a web WHOIS",
        "cbr": "the name, licence type and number and the status of the participant",
        "rkn": "the registration number, date of entry, purposes, cross-border transfer yes/no and the database location",
    }
    if kind == "whois":
        where = "https://tcinet.ru/"
    note = "%s. Open %s in a browser, look up %s and paste back %s." % (reason, where, arg, pastes[kind])
    if kind == "rkn":
        note = ("The operators registry is not scraped. Open %s in a browser from a Russian IP address, "
                "search by INN %s and paste back %s." % (where, arg, pastes[kind]))
    if kind == "npd":
        note += " The NPD service allows at most 2 requests per minute from one IP."
    if wait_hint:
        note += " " + WAIT_HINT_RU % where
    return answer("manual", where, {"key": arg, "paste_back": pastes[kind]}, note)


def failure(kind, arg, exc):
    if isinstance(exc, Blocked):
        reason = {"timeout": "The registry did not answer in time"}.get(
            str(exc), "The registry refused a plain request (%s: anti-bot page, captcha or geo block)" % exc)
        return manual(kind, arg, reason, wait_hint=kind in ("egrul", "npd"))
    url = {"egrul": EGRUL_URL, "npd": NPD_URL, "cbr": CBR_URL % arg, "whois": WHOIS_URL, "rkn": RKN_URL}[kind]
    return answer("error", url, {"key": arg}, "%s; retry later and, if it persists, check by hand." % exc)


# --------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------

def iso_date(value):
    match = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", value or "")
    return "%s-%s-%s" % (match.group(3), match.group(2), match.group(1)) if match else value


def egrul_http(method, url, data=None, headers=None):
    """http() for the EGRUL flow: an error status with a captcha page is Blocked (manual), not a failure."""
    try:
        return http(method, url, data, headers)
    except HttpFailure as exc:
        if looks_like_captcha(exc.body):
            raise Blocked("captcha page, HTTP %s" % exc.code)
        raise


def egrul(arg):
    form = urllib.parse.urlencode({"query": arg, "region": "", "page": "", "vyp3CaptchaToken": ""}).encode("ascii")
    _, body = egrul_http("POST", EGRUL_URL, form, {"Content-Type": "application/x-www-form-urlencoded"})
    start = json_body(body)
    if start is None:
        if looks_like_captcha(body) or looks_like_html(body):
            return manual("egrul", arg, "The registry asks for a captcha or answered with a web page", wait_hint=True)
        return answer("error", EGRUL_URL, {"key": arg}, "unexpected answer of the registry (not JSON)")
    if start.get("captchaRequired"):
        return manual("egrul", arg, "The registry asks for a captcha", wait_hint=True)
    token = start.get("t")
    if not token:
        return answer("error", EGRUL_URL, {"key": arg}, "the registry returned no search token")
    rows = None
    for attempt in range(3):
        _, body = egrul_http("GET", EGRUL_URL + "search-result/" + urllib.parse.quote(str(token), safe=""))
        found = json_body(body)
        if found is None:
            if looks_like_captcha(body) or looks_like_html(body):
                return manual("egrul", arg, "The registry asks for a captcha or answered with a web page",
                              wait_hint=True)
            return answer("error", EGRUL_URL, {"key": arg}, "unexpected search result (not JSON)")
        if found.get("captchaRequired"):
            return manual("egrul", arg, "The registry asks for a captcha", wait_hint=True)
        if isinstance(found.get("rows"), list):
            rows = found["rows"]
            break
        pause(1)
    if rows is None:
        return answer("error", EGRUL_URL, {"key": arg}, "the search result was not ready; retry later")
    if not rows:
        return answer("not_found", EGRUL_URL, {"key": arg})
    row = rows[0]
    data = {"kind": row.get("k"), "name": row.get("n"), "inn": row.get("i"), "ogrn": row.get("o"),
            "registered": iso_date(row.get("r")), "matches": len(rows)}
    if row.get("p"):
        data["kpp"] = row["p"]
    if row.get("e"):
        data["ended"] = iso_date(row["e"])
    return answer("ok", EGRUL_URL, data)


def npd(arg, day):
    payload = json.dumps({"inn": arg, "requestDate": day}).encode("utf-8")
    try:
        _, body = http("POST", NPD_API, payload, {"Content-Type": "application/json"})
    except HttpFailure as exc:
        code = (json_body(exc.body) or {}).get("code", "")
        if code == NPD_LIMIT_CODE:
            return manual("npd", arg, "The NPD service request limit is reached", wait_hint=True)
        if code == NPD_UNAVAILABLE_CODE or exc.code >= 500:
            return manual("npd", arg, "The NPD service is unavailable")
        if looks_like_captcha(exc.body) or looks_like_html(exc.body):
            return manual("npd", arg, "The NPD service answered with a web page", wait_hint=True)
        return answer("error", NPD_URL, {"key": arg}, "The NPD service rejected the request (%s %s): check the "
                      "INN and the date." % (exc.code, code))
    reply = json_body(body)
    if reply is None and (looks_like_captcha(body) or looks_like_html(body)):
        return manual("npd", arg, "The NPD service asks for a captcha or answered with a web page", wait_hint=True)
    if reply is None or not isinstance(reply.get("status"), bool):
        return answer("error", NPD_URL, {"key": arg}, "unexpected answer of the NPD service")
    data = {"inn": arg, "date": day, "is_npd": reply["status"], "message": reply.get("message", "")}
    return answer("ok" if reply["status"] else "not_found", NPD_URL, data)


def parse_whois(text):
    fields = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith(("%", "#")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "nserver":
            fields.setdefault("nserver", []).append(value)
        elif key in WHOIS_KEYS and key not in fields:
            fields[key] = value
    for key in ("created", "paid-till", "free-date"):
        if key in fields:
            fields[key] = fields[key][:10]
    return fields


def whois(domain):
    chunks, total = [], 0
    with socket.create_connection((WHOIS_HOST, 43), timeout=TIMEOUT) as sock:
        sock.sendall((domain + "\r\n").encode("ascii"))
        while total < MAX_BODY:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    text = b"".join(chunks).decode("utf-8", errors="replace")
    if re.search(r"no entries found", text, re.I):
        return answer("not_found", WHOIS_URL, {"domain": domain})
    fields = parse_whois(text)
    if "domain" not in fields:
        return answer("error", WHOIS_URL, {"domain": domain}, "unexpected WHOIS reply: %r" % text[:120])
    return answer("ok", WHOIS_URL, fields)


def cbr(ogrn):
    url = CBR_URL % ogrn
    try:
        _, body = http("GET", url)
    except HttpFailure as exc:
        if exc.code == 404:
            return answer("not_found", url, {"ogrn": ogrn})
        return manual("cbr", ogrn, "The Bank of Russia site answered %s" % exc.code)
    except NetworkFailure as exc:
        return manual("cbr", ogrn, "The Bank of Russia site is not reachable (%s)" % exc)
    page = body.decode("utf-8", errors="replace")
    visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page))
    if re.search(r"не найден|нет данных|не найдена", visible, re.I):
        return answer("not_found", url, {"ogrn": ogrn})
    if ogrn in visible:
        heading = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.I | re.S) or re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        name = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", heading.group(1))).strip() if heading else ""
        return answer("ok", url, {"ogrn": ogrn, "name": name})
    return manual("cbr", ogrn, "The page format was not recognised")


def lookup(kind, key, day):
    if offline():
        names = [key] if kind != "whois" else [key, urllib.parse.unquote(key)]
        stub = stub_answer(kind, names)
        if stub is not None:
            return stub
        if kind != "rkn":
            return answer("error", "", {"key": key}, "offline mode: no stub %s-%s.json in LEGAL_KIT_STUBS" % (kind, key))
        return manual("rkn", key, "")
    if kind == "rkn":
        return manual("rkn", key, "")
    try:
        if kind == "egrul":
            return egrul(key)
        if kind == "npd":
            return npd(key, day)
        if kind == "whois":
            return whois(key)
        return cbr(key)
    except Blocked as exc:
        return failure(kind, key, exc)
    except (HttpFailure, NetworkFailure) as exc:
        return failure(kind, key, exc)
    except (socket.timeout, TimeoutError):
        return failure(kind, key, Blocked("timeout"))
    except OSError as exc:
        return failure(kind, key, NetworkFailure(str(exc)))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="registry.py",
        description="Look up a public registry (egrul, npd, whois, cbr, rkn). Prints JSON. "
                    "LEGAL_KIT_OFFLINE=1 + LEGAL_KIT_STUBS=<dir> read <kind>-<arg>.json instead of the network.")
    parser.add_argument("kind", choices=("egrul", "npd", "whois", "cbr", "rkn"))
    parser.add_argument("arg", help="INN/OGRN (egrul), INN (npd, rkn), domain (whois), OGRN (cbr)")
    parser.add_argument("--date", help="YYYY-MM-DD for npd (default: today)")
    return parser


def main(argv=None):
    args, code = _kb.parse_args(build_parser(), sys.argv[1:] if argv is None else argv)
    if args is None:
        return code
    try:
        key = validate(args.kind, args.arg)
        day = _kb.today_arg(args.date).isoformat() if args.kind == "npd" else None
    except _kb.KbError as exc:
        return _kb.fail(str(exc))
    result = lookup(args.kind, key, day)
    if "kind" not in result:
        result["kind"] = args.kind
        result["key"] = key
    _kb.emit(result)
    return 1 if result["status"] == "error" else 0


if __name__ == "__main__":
    _kb.setup_stdio()
    sys.exit(main())
