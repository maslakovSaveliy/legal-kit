#!/usr/bin/env python3
"""Static scan of a live site. Python 3.9+, standard library only (urllib, html.parser).

Features of features/catalog.json are matched in the page HTML: `hosts` entries (host[/path-prefix]: the
URL host equals the entry host or is a subdomain of it and the path starts with the prefix), `dom` and
`code` regexes. Crawls same-origin pages from the start URL and /sitemap.xml with plain GET requests. It does
not execute JavaScript (`js_executed` is always false), never submits a form, does not follow
redirects to other hosts and does not send cookies back. Page text is data: it is parsed, never
interpreted. Reports pages, forms with checkboxes (consent heuristic, pre-checked state), links
to legal pages, third-party script/iframe/img/link hosts, hosts named in inline scripts and
the Set-Cookie headers (names and flags, no values) of the first response.

A scan stops at --deadline seconds (default 120). On Python < 3.10 runs of `<tag` without `>` longer than
4096 characters are replaced by a closed `<x>` token before parsing, because html.parser is quadratic on
them there.

Exit codes: 0 ok, 1 start page unreachable, 2 bad input.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _kb  # noqa: E402  (must come first: it protects the stdlib `select` module)

import argparse  # noqa: E402
import re  # noqa: E402
import socket  # noqa: E402
import time  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from collections import deque  # noqa: E402
from html.parser import HTMLParser  # noqa: E402
from urllib.parse import urljoin, urlsplit, urlunsplit  # noqa: E402

USER_AGENT = "legal-kit-scan/0.1 (static scan, no JavaScript, never submits forms)"
MAX_REDIRECTS = 5
PER_PAGE_EVIDENCE = 5
MAX_EVIDENCE = 30
SKIP_EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".css", ".js", ".mjs", ".json",
             ".xml", ".zip", ".gz", ".rar", ".mp3", ".mp4", ".webm", ".woff", ".woff2", ".ttf", ".eot", ".docx",
             ".doc", ".xlsx", ".xls", ".txt", ".csv", ".apk", ".ipa"}
LINK_RELS = {"stylesheet", "preconnect", "preload", "dns-prefetch", "prefetch", "modulepreload"}
SKIPPED_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}
LEGAL_LINK_KINDS = (
    ("cookie", re.compile(r"cookie|куки", re.I)),
    ("privacy", re.compile(r"privacy|policy|politika|конфиденциальн|обработк\w*\s+персональн|персональн\w*\s+данн", re.I)),
    ("offer", re.compile(r"oferta|offer|оферт", re.I)),
    ("terms", re.compile(r"terms|soglashenie|agreement|пользовательск\w*\s+соглашени|условия\s+использования", re.I)),
    ("refund", re.compile(r"vozvrat|refund|returns?\b|возврат|обмен", re.I)),
    ("requisites", re.compile(r"rekvizity|requisites|реквизит", re.I)),
    ("contacts", re.compile(r"contacts|контакт", re.I)),
)
LONG_OPEN_TAG = re.compile(r"<[A-Za-z/!?][^>]{4096,}")
DEFAULT_MAX_BYTES = 1024 * 1024
PARSE_CHUNK = 64 * 1024
DEFAULT_DEADLINE = 120.0
URL_IN_TEXT = re.compile(r"""https?://[^\s"'<>\\)\]]+""")
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Surface redirects as responses so the crawler decides whether to follow them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener_for(url):
    host = (urlsplit(url).hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    return urllib.request.build_opener(_NoRedirect)


class Reply:
    def __init__(self, status=None, headers=None, body=b"", location=None, error=None):
        self.status = status
        self.headers = headers
        self.body = body
        self.location = location
        self.error = error

    def header(self, name, default=""):
        return (self.headers.get(name) if self.headers is not None else None) or default


def fetch(url, timeout, max_bytes):
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "ru,en;q=0.8"})
    try:
        response = _opener_for(url).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(max_bytes) if 200 <= exc.code < 300 or exc.code >= 400 else b""
        except Exception:  # noqa: BLE001 - body of an error page is optional
            body = b""
        reply = Reply(exc.code, exc.headers, body, exc.headers.get("Location") if exc.headers else None)
        exc.close()
        return reply
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        return Reply(error="%s: %s" % (type(reason).__name__, reason))
    with response:
        body = response.read(max_bytes + 1)[:max_bytes]
        return Reply(response.status, response.headers, body)


class DeadlineReached(Exception):
    """The --deadline of the whole scan passed."""


def prepare_html(text, force=False):
    """Replace a tag of 4096+ characters (or an opening tag that never reaches '>') by the closed token <x>.

    html.parser is quadratic on such runs before Python 3.10. The whole run is swapped, not truncated: a
    truncated tag would lose its closing quote and swallow the markup after it. Its attributes are lost,
    nothing else is.
    """
    if force or sys.version_info < (3, 10):
        return LONG_OPEN_TAG.sub("<x", text)
    return text


def decode(reply):
    content_type = reply.header("Content-Type")
    match = re.search(r"charset=([\w-]+)", content_type, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)",
                                                                           reply.body[:2048], re.I)
    charset = match.group(1) if match else "utf-8"
    if isinstance(charset, bytes):
        charset = charset.decode("ascii", "ignore")
    try:
        return reply.body.decode(charset, errors="replace")
    except LookupError:
        return reply.body.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# HTML parsing
# --------------------------------------------------------------------------

class PageParser(HTMLParser):
    def __init__(self, page_url):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.title = ""
        self._in_title = False
        self.links = []          # {href, text, in_footer}
        self._link = None
        self._footer_depth = 0
        self.forms = []
        self._form = None
        self._label_stack = []   # {for, text, boxes}
        self._pending = None     # checkbox collecting trailing label text
        self.assets = {"script": set(), "iframe": set(), "img": set(), "link": set()}
        self.inline_scripts = []
        self._script = None

    # -- tags -----------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "footer":
            self._footer_depth += 1
        elif tag == "a" and attrs.get("href"):
            self._link = {"href": attrs["href"], "text": "", "in_footer": self._footer_depth > 0}
        elif tag == "script":
            if attrs.get("src"):
                self.assets["script"].add(urljoin(self.page_url, attrs["src"]))
            elif "json" not in attrs.get("type", "").lower():
                self._script = []
        elif tag == "iframe" and attrs.get("src"):
            self.assets["iframe"].add(urljoin(self.page_url, attrs["src"]))
        elif tag == "img" and attrs.get("src"):
            self.assets["img"].add(urljoin(self.page_url, attrs["src"]))
        elif tag == "link" and attrs.get("href"):
            if LINK_RELS & set(attrs.get("rel", "").lower().split()):
                self.assets["link"].add(urljoin(self.page_url, attrs["href"]))
        elif tag == "form":
            self._close_form()
            self._form = {"page": self.page_url,
                          "action": urljoin(self.page_url, attrs.get("action", "")) if attrs.get("action") else self.page_url,
                          "method": (attrs.get("method") or "get").lower(), "fields": [], "checkboxes": [],
                          "_labels_for": {}}
        elif tag == "label":
            self._end_pending()
            self._label_stack.append({"for": attrs.get("for"), "text": [], "boxes": []})
        elif tag in ("input", "textarea", "select", "button"):
            self._end_pending()
            if self._form is not None:
                self._form_control(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "footer" and self._footer_depth:
            self._footer_depth -= 1
        elif tag == "a" and self._link is not None:
            self._link["text"] = re.sub(r"\s+", " ", self._link["text"]).strip()
            self.links.append(self._link)
            self._link = None
        elif tag == "script" and self._script is not None:
            self.inline_scripts.append("".join(self._script))
            self._script = None
        elif tag == "label" and self._label_stack:
            label = self._label_stack.pop()
            text = re.sub(r"\s+", " ", "".join(label["text"])).strip()
            for box in label["boxes"]:
                box["label"] = (box["label"] + " " + text).strip()
            if label["for"] and self._form is not None:
                self._form["_labels_for"][label["for"]] = text
        elif tag == "form":
            self._close_form()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._link is not None:
            self._link["text"] += data
        if self._script is not None:
            self._script.append(data)
        for label in self._label_stack:
            label["text"].append(data)
        if self._pending is not None and len(self._pending["label"]) < 160:
            self._pending["label"] = (self._pending["label"] + " " + data.strip()).strip()

    # -- forms ----------------------------------------------------------
    def _form_control(self, tag, attrs):
        name = attrs.get("name") or attrs.get("id") or ""
        input_type = attrs.get("type", "text").lower() if tag == "input" else tag
        if tag == "input" and input_type == "checkbox":
            box = {"name": name, "id": attrs.get("id", ""), "label": "", "consent": False,
                   "prechecked": "checked" in attrs}
            for label in self._label_stack:
                label["boxes"].append(box)
            self._form["checkboxes"].append(box)
            if not self._label_stack:  # text of an enclosing <label> is added when the label closes
                self._pending = box
        elif tag == "button" or input_type in SKIPPED_INPUT_TYPES:
            return
        elif name and name not in self._form["fields"]:
            self._form["fields"].append(name)

    def _end_pending(self):
        self._pending = None

    def _close_form(self):
        form = self._form
        if form is None:
            return
        self._end_pending()
        labels_for = form.pop("_labels_for")
        for box in form["checkboxes"]:
            extra = labels_for.get(box.pop("id"))
            if extra and extra not in box["label"]:
                box["label"] = (box["label"] + " " + extra).strip()
            box["label"] = box["label"][:160]
            box["consent"] = bool(_kb.CONSENT_RE.search(box["name"] + " " + box["label"]))
        form["has_consent_checkbox"] = any(box["consent"] for box in form["checkboxes"])
        form["prechecked"] = any(box["consent"] and box["prechecked"] for box in form["checkboxes"])
        self.forms.append(form)
        self._form = None

    def close(self):
        super().close()
        self._close_form()


# --------------------------------------------------------------------------
# Crawl
# --------------------------------------------------------------------------

def normalize(url):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def site_key(url):
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def origin_key(url):
    """(host without www., port) with default ports folded together, for the same-origin test."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = -1
    return site_key(url), 0 if port in (None, 80, 443) else port


def crawlable(url):
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and os.path.splitext(parts.path)[1].lower() not in SKIP_EXTS


def legal_kind(url, text):
    haystack = "%s %s" % (urlsplit(url).path, text)
    for kind, regex in LEGAL_LINK_KINDS:
        if regex.search(haystack):
            return kind
    return None


def parse_cookie(header):
    parts = [p.strip() for p in header.split(";")]
    name = parts[0].split("=", 1)[0].strip()
    attrs = {}
    for part in parts[1:]:
        key, _, value = part.partition("=")
        attrs[key.strip().lower()] = value.strip()
    max_age = attrs.get("max-age")
    return {"name": name, "secure": "secure" in attrs, "httponly": "httponly" in attrs,
            "samesite": attrs.get("samesite") or None, "domain": attrs.get("domain") or None,
            "path": attrs.get("path") or None, "max_age": int(max_age) if max_age and max_age.lstrip("-").isdigit() else None,
            "expires": attrs.get("expires") or None}


class Crawler:
    def __init__(self, start, max_pages, timeout, delay, max_bytes, catalog=None, deadline=DEFAULT_DEADLINE):
        self.start = start
        self.deadline = time.monotonic() + deadline
        self.deadline_reached = False
        self.catalog = catalog
        self.evidence = {}
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay
        self.max_bytes = max_bytes
        self.requests = 0
        self.origin = None
        self.pages, self.skipped, self.errors = [], [], []
        self.forms, self._form_keys = [], {}
        self.links = {}
        self.assets = {"script": set(), "iframe": set(), "img": set(), "link": set()}
        self.inline_hosts = set()
        self.cookies = []
        self.first_status = None
        self.sitemap = {"url": None, "found": False, "urls": [], "total": 0}

    def get(self, url):
        if time.monotonic() > self.deadline:
            raise DeadlineReached()
        if self.requests and self.delay:
            time.sleep(self.delay)
        self.requests += 1
        return fetch(url, self.timeout, self.max_bytes)

    def get_following(self, url, cookie_headers=None):
        """GET with same-site redirects only; returns (reply, final_url, redirected_offsite_url).

        Every Set-Cookie header of the redirect chain is appended to `cookie_headers`.
        """
        for _ in range(MAX_REDIRECTS + 1):
            reply = self.get(url)
            if cookie_headers is not None and reply.headers is not None:
                cookie_headers.extend(reply.headers.get_all("Set-Cookie") or [])
            if reply.status and 300 <= reply.status < 400 and reply.location:
                target = urljoin(url, reply.location)
                if urlsplit(target).scheme not in ("http", "https") or origin_key(target) != origin_key(self.start):
                    return reply, url, target
                url = target
                continue
            return reply, url, None
        return Reply(error="too many redirects"), url, None

    def run(self):
        try:
            self.crawl()
        except DeadlineReached:
            self.deadline_reached = True
            self.errors.append({"url": None, "error": "deadline reached: the scan was cut short"})

    def crawl(self):
        cookie_headers = []
        reply, final, offsite = self.get_following(self.start, cookie_headers)
        if reply.error or offsite:
            self.errors.append({"url": self.start, "error": reply.error or "redirect to %s" % offsite})
            return
        self.first_status = reply.status
        for header in cookie_headers:
            cookie = parse_cookie(header)
            if cookie not in self.cookies:
                self.cookies.append(cookie)
        parts = urlsplit(final)
        self.origin = "%s://%s" % (parts.scheme, parts.netloc)
        queue, seen = deque(), {normalize(final)}
        self.process(final, reply, queue, seen)
        self.read_sitemap(queue, seen)
        while queue and len(self.pages) < self.max_pages:
            url = queue.popleft()
            reply, final, offsite = self.get_following(url)
            if offsite:
                self.skipped.append({"url": url, "reason": "redirect_offsite", "target": offsite})
                continue
            if reply.error:
                self.errors.append({"url": url, "error": reply.error})
                continue
            if normalize(final) != normalize(url):
                if normalize(final) in seen:
                    continue
                seen.add(normalize(final))
            self.process(final, reply, queue, seen)

    def same_origin(self, url):
        return urlsplit(url).scheme in ("http", "https") and origin_key(url) == origin_key(self.origin)

    def process(self, url, reply, queue, seen):
        record = {"url": url, "status": reply.status, "content_type": reply.header("Content-Type").split(";")[0],
                  "bytes": len(reply.body), "title": ""}
        self.pages.append(record)
        if not (200 <= reply.status < 300) or "html" not in record["content_type"].lower():
            return
        parser = PageParser(url)
        text = decode(reply)
        try:
            prepared = prepare_html(text)
            for start in range(0, len(prepared), PARSE_CHUNK):
                if time.monotonic() > self.deadline:  # a slow page must not outlive the scan deadline
                    raise DeadlineReached()
                parser.feed(prepared[start:start + PARSE_CHUNK])
            parser.close()
        except DeadlineReached:
            raise
        except Exception as exc:  # noqa: BLE001 - malformed markup must not stop the crawl
            self.errors.append({"url": url, "error": "parse: %s" % exc})
        record["title"] = re.sub(r"\s+", " ", parser.title).strip()[:200]
        self.collect(url, parser)
        self.match_features(url, text)
        for link in parser.links:
            target = urljoin(url, link["href"]).split("#")[0]
            if not crawlable(target):
                continue
            if self.same_origin(target) and normalize(target) not in seen:
                seen.add(normalize(target))
                queue.append(target)

    def collect(self, url, parser):
        page_host = site_key(self.origin)
        for link in parser.links:
            href = link["href"].strip()
            if href.startswith(("#", "mailto:", "tel:", "javascript:", "sms:")):
                continue
            target = urljoin(url, href).split("#")[0]
            kind = legal_kind(target, link["text"])
            if not kind or not target.startswith(("http://", "https://")):
                continue
            entry = self.links.setdefault((kind, target), {
                "kind": kind, "url": target, "text": link["text"][:120], "found_on": [], "in_footer": False,
                "same_origin": self.same_origin(target)})
            if url not in entry["found_on"]:
                entry["found_on"].append(url)
            entry["in_footer"] = entry["in_footer"] or link["in_footer"]
        for kind, urls in parser.assets.items():
            for asset in urls:
                host = urlsplit(asset).hostname
                if host and site_key(asset) != page_host and asset.startswith(("http://", "https://")):
                    self.assets[kind].add(host.lower())
        for script in parser.inline_scripts:
            for found in URL_IN_TEXT.findall(script):
                host = urlsplit(found).hostname
                if host and site_key(found) != page_host:
                    self.inline_hosts.add(host.lower())
        for form in parser.forms:
            key = (form["action"], form["method"], tuple(form["fields"]), tuple(b["name"] for b in form["checkboxes"]))
            if key in self._form_keys:
                other = self._form_keys[key].setdefault("also_on", [])
                if url not in other and len(other) < 10:
                    other.append(url)
            else:
                self._form_keys[key] = form
                self.forms.append(form)

    def match_features(self, url, html):
        if self.catalog is None:
            return
        found = [(fid, matched, "host") for _, matched, fid in self.catalog.hosts.find_in(html)]
        found.extend((fid, matched, "pattern") for fid, _, matched in
                     self.catalog.pattern_matches(html, per_pattern=PER_PAGE_EVIDENCE))
        per_page = {}
        for feature_id, matched, kind in found:
            bucket = self.evidence.setdefault(feature_id, [])
            item = {"page": url, "match": re.sub(r"\s+", " ", matched).strip()[:120], "kind": kind}
            if per_page.get(feature_id, 0) < PER_PAGE_EVIDENCE and len(bucket) < MAX_EVIDENCE and item not in bucket:
                bucket.append(item)
                per_page[feature_id] = per_page.get(feature_id, 0) + 1

    def read_sitemap(self, queue, seen):
        base = self.origin + "/sitemap.xml"
        self.sitemap["url"] = base
        pending, fetched, found = [base], 0, []
        while pending and fetched < 4:
            reply, _, _ = self.get_following(pending.pop(0))
            fetched += 1
            if reply.error or not reply.status or reply.status >= 400:
                continue
            if fetched == 1:
                self.sitemap["found"] = True
            text = decode(reply)
            locs = LOC_RE.findall(text)
            if "<sitemapindex" in text.lower():
                pending.extend(loc for loc in locs if self.same_origin(loc))
                continue
            found.extend(locs)
        listed = set()
        for loc in found:
            loc = loc.split("#")[0]
            if not self.same_origin(loc):
                if len(self.skipped) < 50:
                    self.skipped.append({"url": loc, "reason": "sitemap_offsite"})
                continue
            if loc not in listed:
                listed.add(loc)
                self.sitemap["urls"].append(loc)
            if crawlable(loc) and normalize(loc) not in seen:
                seen.add(normalize(loc))
                queue.append(loc)
        self.sitemap["total"] = len(self.sitemap["urls"])
        self.sitemap["urls"] = self.sitemap["urls"][:200]


def scan(url, max_pages, timeout, delay, max_bytes, catalog=None, warnings=(), deadline=DEFAULT_DEADLINE):
    crawler = Crawler(url, max_pages, timeout, delay, max_bytes, catalog, deadline)
    crawler.run()
    result = {
        "url": url,
        "origin": crawler.origin,
        "scanned_at": _kb.utc_now(),
        "js_executed": False,
        "deadline_reached": crawler.deadline_reached,
        "requests": crawler.requests,
        "pages": crawler.pages,
        "skipped": crawler.skipped,
        "errors": crawler.errors,
        "sitemap": crawler.sitemap,
        "legal_links": sorted(crawler.links.values(), key=lambda e: (e["kind"], e["url"])),
        "features": [{"id": fid, "evidence": items} for fid, items in sorted(crawler.evidence.items()) if items],
        "forms": crawler.forms,
        "third_party": {kind: sorted(hosts) for kind, hosts in crawler.assets.items()},
        "inline_script_hosts": sorted(crawler.inline_hosts),
        "cookies": crawler.cookies,
        "warnings": list(warnings),
    }
    if crawler.origin is None:
        result["error"] = crawler.errors[0]["error"] if crawler.errors else "start page unreachable"
    elif crawler.first_status in (401, 403, 429, 503):
        result["blocked"] = True
        result["note"] = ("The site answered %s to a plain request (anti-bot page, geo block or login). "
                          "Do not work around it: ask the user to open the page and paste what is needed."
                          % crawler.first_status)
    return result


def build_parser():
    parser = argparse.ArgumentParser(
        prog="scan_url.py",
        description="Static scan of a live site (no JavaScript, forms are never submitted). Prints JSON.")
    parser.add_argument("url", help="start URL (http or https)")
    parser.add_argument("--max-pages", type=int, default=30, help="pages to fetch (default 30)")
    parser.add_argument("--timeout", type=float, default=10.0, help="seconds per request (default 10)")
    parser.add_argument("--delay", type=float, default=0.3, help="pause between requests in seconds (default 0.3)")
    parser.add_argument("--catalog", help="feature catalog JSON (default: references/features/catalog.json)")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="bytes read per page (default 1 MB)")
    parser.add_argument("--deadline", type=float, default=DEFAULT_DEADLINE,
                        help="stop the whole scan after this many seconds (default 120)")
    return parser


def main(argv=None):
    args, code = _kb.parse_args(build_parser(), sys.argv[1:] if argv is None else argv)
    if args is None:
        return code
    parts = urlsplit(args.url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return _kb.fail("URL must start with http:// or https:// and name a host: %s" % args.url)
    if (not 1 <= args.max_pages <= 500 or args.timeout <= 0 or args.delay < 0 or args.max_bytes < 1024
            or args.deadline <= 0):
        return _kb.fail("--max-pages must be 1..500, --timeout > 0, --delay >= 0, --max-bytes >= 1024, "
                        "--deadline > 0")
    catalog, warnings = None, []
    catalog_path = args.catalog or _kb.DEFAULT_CATALOG
    if args.catalog or os.path.isfile(catalog_path):
        try:
            catalog = _kb.load_catalog(catalog_path)
        except _kb.KbError as exc:
            return _kb.fail(str(exc))
        warnings.extend(catalog.warnings)
    else:
        warnings.append("feature catalog not found at %s: features are not matched" % catalog_path)
    result = scan(args.url, args.max_pages, args.timeout, args.delay, args.max_bytes, catalog, warnings,
                  args.deadline)
    _kb.emit(result)
    return 1 if "error" in result else 0


if __name__ == "__main__":
    _kb.setup_stdio()
    sys.exit(main())
