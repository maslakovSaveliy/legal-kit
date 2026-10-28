"""Tests for the stdlib scripts shipped inside the skill (skills/legal-kit/scripts).

No network: the URL scanner talks to a local http.server, the registry client is
tested with mocked urlopen/socket and offline stubs. The scripts are loaded by
path, because select.py has the name of a stdlib module.
"""

import ast
import contextlib
import functools
import http.server
import importlib
import importlib.util
import io
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# Preload before the scripts directory joins sys.path: select.py there must not
# shadow the stdlib module of the same name.
import select  # noqa: F401
import selectors  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "legal-kit" / "scripts"
REAL_KB = ROOT / "skills" / "legal-kit" / "references" / "jurisdictions" / "ru"
FIX = Path(__file__).resolve().parent / "fixtures" / "scripts"
KB = FIX / "kb"
CATALOG = FIX / "catalog.json"
REAL_CATALOG = ROOT / "skills" / "legal-kit" / "references" / "features" / "catalog.json"
ANSWERS = FIX / "docs" / "answers.json"
TODAY = "2026-10-18"
SCRIPT_NAMES = ["_kb", "scan_repo", "scan_url", "select", "registry", "check_docs", "report"]

# Checksum vectors computed with the INN/OGRN algorithms; fictitious numbers
# (region code 00 does not exist).
INN10_OK = ["0098765437", "0013579240", "0012345017"]
INN10_BAD = "0098765438"
INN12_OK = ["009876543299", "001357924634", "001234500177"]
INN12_BAD = "009876543298"
OGRN13_OK = ["1020000000008", "1000000000000"]
OGRN13_BAD = "1020000000009"
OGRN15_OK = ["322000000000012", "304000000000018"]
OGRN15_BAD = "304000000000019"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load(name):
    """Import one script by file path under a unique module name."""
    path = SCRIPTS / f"{name}.py"
    if not path.is_file():
        pytest.fail(f"script not written yet: {path}")
    module_name = name if name == "_kb" else f"legalkit_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_main(name, argv, capsys):
    """Run script.main(argv) in-process; return (exit code, stdout text)."""
    module = load(name)
    capsys.readouterr()
    code = module.main([str(a) for a in argv])
    out = capsys.readouterr().out
    return code, out


def run_json(name, argv, capsys):
    code, out = run_main(name, argv, capsys)
    return code, json.loads(out)


def run_cli(name, *argv, env=None, cwd=None):
    full_env = dict(os.environ)
    full_env.pop("LEGAL_KIT_OFFLINE", None)
    full_env.pop("LEGAL_KIT_STUBS", None)
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPTS / f"{name}.py"), *map(str, argv)],
        capture_output=True, text=True, env=full_env, cwd=cwd, timeout=60,
    )


# --------------------------------------------------------------------------
# Packaging of the scripts themselves
# --------------------------------------------------------------------------

def test_all_scripts_exist():
    missing = [n for n in SCRIPT_NAMES if not (SCRIPTS / f"{n}.py").is_file()]
    assert not missing, f"missing scripts: {missing}"


@pytest.mark.parametrize("name", SCRIPT_NAMES)
def test_script_is_py39_syntax_and_stdlib_only(name):
    path = SCRIPTS / f"{name}.py"
    assert path.is_file(), path
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 9))
    assert ast.get_docstring(tree), f"{name}.py needs a module docstring"
    assert "stdlib" in ast.get_docstring(tree).lower() or "standard library" in ast.get_docstring(tree).lower()
    local = set(SCRIPT_NAMES)
    for node in ast.walk(tree):
        modules = []
        if isinstance(node, ast.Import):
            modules = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        for module in modules:
            top = module.split(".")[0]
            assert top in sys.stdlib_module_names or top in local, f"{name}.py imports non-stdlib {module}"


@pytest.mark.parametrize("name", [n for n in SCRIPT_NAMES if n != "_kb"])
def test_help_exits_zero(name):
    result = run_cli(name, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()


def test_select_py_does_not_shadow_stdlib_select():
    code = (
        "import sys; sys.path.insert(0, %r); import _kb; import select; "
        "print(getattr(select, '__file__', 'builtin')); print(hasattr(select, 'select'))"
    ) % str(SCRIPTS)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert not lines[0].startswith(str(SCRIPTS)), "stdlib select was shadowed by scripts/select.py"
    assert lines[-1] == "True"


def test_network_scripts_run_from_scripts_dir_with_select_py_beside_them():
    # Running `python scripts/registry.py` puts scripts/ first on sys.path.
    result = run_cli("registry", "whois", "bad domain!")
    assert result.returncode == 2, result.stderr


# --------------------------------------------------------------------------
# _kb
# --------------------------------------------------------------------------

def test_kb_allowlist_and_platform_domains():
    kb = load("_kb")
    assert "pravo.gov.ru" in kb.ALLOWLIST and "kremlin.ru" in kb.ALLOWLIST and "*.gov.ru" in kb.ALLOWLIST
    assert set(kb.PLATFORM_DOMAINS) == {"developer.apple.com", "support.google.com", "rustore.ru", "developer.huawei.com",
                                        "developer.android.com"}
    good = [
        "https://pravo.gov.ru/proxy/ips/?docbody=&nd=1", "http://publication.pravo.gov.ru/document/1",
        "https://www.vsrf.ru/x", "https://ksrf.ru/", "https://www.cbr.ru/finorg/", "https://egrul.nalog.ru/",
        "https://sozd.duma.gov.ru/bill/1", "https://regulation.gov.ru/p/1", "http://kremlin.ru/acts",
        "https://rkn.gov.ru/x", "https://minjust.gov.ru/ru/", "https://PRAVO.GOV.RU:443/x",
    ]
    bad = [
        "https://rg.ru/doc", "https://pravo.gov.ru.evil.example/x", "https://evilgov.ru/",
        "https://pravo.gov.ru@evil.example/", "ftp://pravo.gov.ru/x", "not a url", "", "https://consultant.ru/d",
        "javascript:alert(1)",
        "https://evil.test\\@pravo.gov.ru/",  # a browser reads the backslash as a slash: host is evil.test
        "https://user@pravo.gov.ru/", "https://pravo.gov.ru\t.evil.test/", "https://pravo.gov.ru_x.evil.test/",
    ]
    for url in good:
        assert kb.is_allowlisted(url), url
    for url in bad:
        assert not kb.is_allowlisted(url), url
    assert kb.is_platform_url("https://developer.apple.com/app-store/review/")
    assert kb.is_platform_url("https://www.rustore.ru/help")
    assert kb.is_platform_url("https://developer.android.com/distribute/play-policies")
    assert not kb.is_platform_url("https://example.com/developer.apple.com")


def test_host_lookup_is_bounded_on_pathological_input():
    index = load("_kb").HostIndex()
    index.add("web", "mc.yandex.ru")
    index.add("tg", "telegram.org/js/telegram-widget")
    started = time.monotonic()
    for text in ("a." * 200000 + "com", "a" * 300000, "a-" * 100000 + ".com", "a." * 100 + "mc.yandex.ru/x",
                 ("a." * 130 + "mc.yandex.ru ") * 500, "http://" + "a." * 5000 + "mc.yandex.ru/x"):
        list(index.find_in(text))
    assert time.monotonic() - started < 1
    assert index.lookup("a." * 127 + "mc.yandex.ru") == []  # more than 127 labels: refused
    assert index.lookup("x" * 254 + ".mc.yandex.ru") == []  # more than 253 characters: refused
    assert index.lookup("a." * 100 + "mc.yandex.ru") == ["web"]
    assert index.lookup("deep.sub.mc.yandex.ru") == ["web"]  # only as many trailing labels as an entry has are tried


def test_kb_inn_checksum():
    kb = load("_kb")
    for value in INN10_OK + INN12_OK:
        assert kb.inn_valid(value), value
    for value in (INN10_BAD, INN12_BAD, "123", "12345678901", "00987654a7", "", None):
        assert not kb.inn_valid(value), value


def test_kb_ogrn_checksum():
    kb = load("_kb")
    for value in OGRN13_OK + OGRN15_OK:
        assert kb.ogrn_valid(value), value
    for value in (OGRN13_BAD, OGRN15_BAD, "12345", "102000000000", "10200000000a8", "", None):
        assert not kb.ogrn_valid(value), value


def test_kb_loaders_on_mini_kb():
    kb = load("_kb")
    reqs = kb.load_requirements(KB)
    assert len(reqs) == 19 and reqs["ru:t-always"]["dir"] == "A"
    elements = kb.load_elements(KB)
    assert elements["tpl-policy:А1"]["status"] == "обязательно"
    assert kb.base_date(KB) == "2026-10-16"


def test_kb_loaders_on_real_kb():
    kb = load("_kb")
    reqs = kb.load_requirements(REAL_KB)
    assert len(reqs) >= 200 and all(i.startswith("ru:") for i in reqs)
    elements = kb.load_elements(REAL_KB)
    assert len(elements) >= 300 and all(":" in key for key in elements)
    assert kb.base_date(REAL_KB)


def test_kb_loader_errors(tmp_path):
    kb = load("_kb")
    with pytest.raises(kb.KbError):
        kb.load_requirements(tmp_path)
    (tmp_path / "requirements.jsonl").write_text('{"id": "ru:a"}\nnot json\n', encoding="utf-8")
    with pytest.raises(kb.KbError) as err:
        kb.load_requirements(tmp_path)
    assert "line 2" in str(err.value)


# --------------------------------------------------------------------------
# select.py
# --------------------------------------------------------------------------

def select_args(*extra):
    return ["--kb", KB, "--today", TODAY, *extra]


def ids(items):
    return sorted(i["id"] for i in items)


def test_select_features_and_always(capsys):
    code, out = run_json("select", select_args("--features", "analytics.web_counter",
                                               "--subject", "ul", "--models", "b2c", "--products", "site"), capsys)
    assert code == 0
    # --models b2c is also the owner fact "b2c"
    assert ids(out["applicable"]) == ["ru:t-always", "ru:t-analytics", "ru:t-b2c", "ru:t-ul-only"]
    why = {i["id"]: i["why"] for i in out["applicable"]}
    assert why["ru:t-always"] == ["always"]
    assert why["ru:t-analytics"] == ["feature:analytics.web_counter"]
    assert why["ru:t-b2c"] == ["owner:b2c"]
    reasons = {i["id"]: i["reason"] for i in out["not_applicable"]}
    assert "ru:t-ios" in reasons and "products" in reasons["ru:t-ios"]
    assert out["templates"] == ["tpl-agreement", "tpl-banner", "tpl-policy", "tpl-seller"]  # not tpl-never
    assert out["template_reasons"]["tpl-banner"] == ["feature:analytics.web_counter"]
    assert out["owner_questions"] == ["ru:t-always"]
    assert [d["path"] for d in out["documents"]] == ["documents/doc-always.md", "documents/doc-analytics.md"]
    assert out["documents"][1]["why"] == ["feature:analytics.web_counter"]
    assert out["warnings"] == []


def test_select_filters_by_subject_models_products(capsys):
    code, out = run_json("select", select_args("--features", "analytics.web_counter,payments.online",
                                               "--subject", "npd", "--models", "b2b", "--products", "ios"), capsys)
    assert code == 0
    applicable = ids(out["applicable"])
    assert "ru:t-ul-only" not in applicable  # subject ul only
    assert "ru:t-b2c" not in applicable  # b2c only
    assert "ru:t-ios" in applicable  # ios allowed
    reasons = {i["id"]: i["reason"] for i in out["not_applicable"]}
    assert "subject" in reasons["ru:t-ul-only"]
    assert "models" in reasons["ru:t-b2c"]


def test_select_does_not_filter_on_axes_left_out(capsys):
    code, out = run_json("select", select_args("--features", "analytics.web_counter"), capsys)
    assert code == 0
    assert {"ru:t-ios", "ru:t-ul-only", "ru:t-analytics", "ru:t-always"} <= set(ids(out["applicable"]))


def test_select_sectoral_only_when_sector_passed(capsys):
    _, without = run_json("select", select_args("--subject", "ul"), capsys)
    assert "ru:t-medical" not in ids(without["applicable"])
    _, with_sector = run_json("select", select_args("--subject", "ul", "--sectors", "medical"), capsys)
    medical = [i for i in with_sector["applicable"] if i["id"] == "ru:t-medical"]
    assert medical and medical[0]["why"] == ["sector:medical"]
    assert "tpl-medical" in with_sector["templates"]
    # an IP is still a subject of the medical requirement; a foreign owner is filtered out
    _, foreign = run_json("select", select_args("--subject", "foreign", "--sectors", "medical"), capsys)
    assert "ru:t-medical" not in ids(foreign["applicable"])


def test_select_future_from(capsys):
    _, out = run_json("select", select_args("--features", "ads.future"), capsys)
    future = {i["id"]: i["future_from"] for i in out["applicable"]}
    assert future["ru:t-future"] == "2027-03-01"
    assert future["ru:t-mixed"] == "2027-09-01"  # latest norm date wins, 'mixed' is ignored
    assert future["ru:t-always"] is None
    _, later = run_json("select", ["--kb", KB, "--today", "2027-10-01", "--features", "ads.future"], capsys)
    assert {i["future_from"] for i in later["applicable"]} == {None}


def test_select_answers_file_supplies_owner_facts(capsys):
    code, out = run_json("select", select_args("--answers", ANSWERS), capsys)
    assert code == 0
    why = {i["id"]: i["why"] for i in out["applicable"]}
    assert "owner:b2c" in why["ru:t-b2c"]
    assert "owner:revenue_over_20m" in why["ru:t-revenue"]
    assert "sector:medical" in why["ru:t-medical"]  # business.sectors are owner-confirmed
    assert "ru:t-minors" not in why  # minors: none
    assert "ru:t-npd-only" not in why  # owner is a legal entity
    assert out["inputs"]["subject"] == "ul" and out["inputs"]["models"] == ["b2c"]
    assert out["inputs"]["products"] == ["site"]


def test_select_answers_minors_and_npd(tmp_path, capsys):
    answers = json.loads(ANSWERS.read_text(encoding="utf-8"))
    answers["owner"]["status"] = "npd"
    answers["audience"]["minors"] = "under-14"
    answers["business"]["sectors"] = []
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers), encoding="utf-8")
    _, out = run_json("select", select_args("--answers", path), capsys)
    why = {i["id"]: i["why"] for i in out["applicable"]}
    assert "owner:subject:npd" in why["ru:t-npd-only"]
    assert "owner:minors" in why["ru:t-minors"]
    assert "ru:t-medical" not in why and "ru:t-ul-only" not in why


def test_select_flags_override_answers(capsys):
    _, out = run_json("select", select_args("--answers", ANSWERS, "--subject", "ip", "--sectors", ""), capsys)
    assert out["inputs"]["subject"] == "ip"
    assert "ru:t-medical" not in ids(out["applicable"])


def test_select_facts_flag(capsys):
    _, out = run_json("select", select_args("--facts", "minors,revenue_over_20m"), capsys)
    assert {"ru:t-minors", "ru:t-revenue"} <= set(ids(out["applicable"]))


def test_select_not_detectable_lists_only_ids_that_nothing_else_triggers(capsys):
    _, out = run_json("select", select_args("--subject", "ul"), capsys)
    # t-offmap is only in not_detectable; t-always is already applicable; t-offmap-npd does not fit an ul owner
    assert out["not_detectable"] == [{"id": "ru:t-offmap", "reason": "cannot be seen in code or pages"}]
    _, npd = run_json("select", select_args("--subject", "npd"), capsys)
    assert [i["id"] for i in npd["not_detectable"]] == ["ru:t-offmap", "ru:t-offmap-npd"]


def test_select_sectoral_requirement_needs_a_confirmed_sector_even_via_a_feature(capsys):
    _, out = run_json("select", select_args("--features", "clinic.keyword", "--subject", "ul"), capsys)
    reasons = {i["id"]: i["reason"] for i in out["not_applicable"]}
    assert reasons["ru:t-medical"] == "sectoral: no confirmed sector"
    assert "ru:t-medical" not in ids(out["applicable"])
    _, confirmed = run_json("select", select_args("--features", "clinic.keyword", "--subject", "ul",
                                                  "--sectors", "medical"), capsys)
    why = {i["id"]: i["why"] for i in confirmed["applicable"]}
    assert why["ru:t-medical"] == ["feature:clinic.keyword", "sector:medical"]


def test_select_domain_ru_fact_from_product_urls(tmp_path, capsys):
    base = json.loads(ANSWERS.read_text(encoding="utf-8"))
    for urls, expected in ((["https://shop.example.test"], False), (["https://shop.ru/"], True),
                           (["https://магазин.рф"], True), (["https://shop.xn--p1ai"], True), (["https://x.su"], True),
                           (["https://shop.ru.evil.com"], False), (["https://shop.com", "http://b.ru:8080/a"], True),
                           ([], False)):
        base["product"]["urls"] = urls
        path = tmp_path / "answers.json"
        path.write_text(json.dumps(base), encoding="utf-8")
        _, out = run_json("select", select_args("--answers", path), capsys)
        why = {i["id"]: i["why"] for i in out["applicable"]}
        assert ("ru:t-domain-ru" in why) is expected, urls
        if expected:
            assert why["ru:t-domain-ru"] == ["owner:domain_ru"]
            assert "tpl-ru" in out["templates"]


def test_select_templates_and_documents_follow_features_and_facts_not_requirement_ids(capsys):
    _, plain = run_json("select", select_args("--subject", "ul"), capsys)
    assert plain["templates"] == ["tpl-policy", "tpl-seller"]  # products unknown: tpl-seller is not suppressed
    assert [d["name"] for d in plain["documents"]] == ["doc-always"]
    _, npd = run_json("select", select_args("--subject", "npd", "--facts", "revenue_over_20m"), capsys)
    assert "tpl-npd" in npd["templates"] and npd["template_reasons"]["tpl-npd"] == ["fact:subject:npd"]
    medical = {d["name"]: d["why"] for d in npd["documents"]}
    assert medical["doc-medical"] == ["fact:subject:npd", "fact:revenue_over_20m"]
    _, sector = run_json("select", select_args("--subject", "ul", "--sectors", "medical"), capsys)
    assert "tpl-medical" in sector["templates"]  # a confirmed sector counts as a fact
    assert "tpl-never" not in plain["templates"] + npd["templates"] + sector["templates"]


def test_select_rule_without_and_products(capsys):
    args = ("--features", "analytics.web_counter", "--subject", "ul")
    _, shop = run_json("select", select_args(*args, "--features", "analytics.web_counter,payments.online"), capsys)
    assert "tpl-agreement" not in shop["templates"]  # "without": a commerce feature was found
    assert "doc-analytics" not in [d["name"] for d in shop["documents"]]
    assert "tpl-banner" in shop["templates"]  # rules without "without" are unaffected
    _, site = run_json("select", select_args(*args), capsys)
    assert {"tpl-agreement"} <= set(site["templates"]) and "doc-analytics" in [d["name"] for d in site["documents"]]
    # "products": fires only when the product kinds intersect; unknown kinds do not suppress it
    for products, expected in (("site", True), ("webapp,ios", True), ("ios", False), ("ios,android", False)):
        _, out = run_json("select", select_args(*args, "--products", products), capsys)
        assert ("tpl-seller" in out["templates"]) is expected, products
    assert "tpl-seller" in site["templates"]


def test_select_notes_ride_on_applicable_items(capsys):
    _, out = run_json("select", select_args("--subject", "ul", "--sectors", "medical"), capsys)
    notes = {i["id"]: i["note"] for i in out["applicable"]}
    assert notes["ru:t-always"] == "Note for tests: applies to everyone"
    assert notes["ru:t-medical"] == "Only a clinic"
    assert notes["ru:t-ul-only"] is None  # no note: the key is still there
    _, plain = run_json("select", select_args("--subject", "ul"), capsys)
    assert "ru:t-medical" not in {i["id"] for i in plain["applicable"]}


def test_select_wrong_answers_types_exit_2_with_a_message(tmp_path, capsys):
    base = json.loads(ANSWERS.read_text(encoding="utf-8"))
    bad = [
        ("business", ["medical"]), ("owner", "ul"), ("product", 5), ("audience", True),
        ("owner.status", ["ul"]), ("product.urls", "https://x.ru"), ("product.urls", [1]), ("business.sectors", "medical"),
        ("product.kinds", {"site": 1}), ("audience.minors", 14),
    ]
    for key, value in bad:
        answers = json.loads(json.dumps(base))
        if "." in key:
            section, field = key.split(".")
            answers[section][field] = value
        else:
            answers[key] = value
        path = tmp_path / "answers.json"
        path.write_text(json.dumps(answers), encoding="utf-8")
        module = load("select")
        capsys.readouterr()
        code = module.main(["--kb", str(KB), "--today", TODAY, "--answers", str(path)])
        captured = capsys.readouterr()
        assert code == 2, key
        assert key.split(".")[-1] in captured.err and "Traceback" not in captured.err, key
        assert json.loads(captured.out)["error"]
    # null sections and fields are fine (unknown)
    answers = json.loads(json.dumps(base))
    answers.update(business=None, audience=None, product=None)
    answers["owner"]["status"] = None
    path = tmp_path / "answers.json"
    path.write_text(json.dumps(answers), encoding="utf-8")
    assert run_main("select", select_args("--answers", path), capsys)[0] == 0


def test_check_docs_wrong_answers_owner_type_exits_2(tmp_path, capsys):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"owner": ["ООО"]}), encoding="utf-8")
    doc = write(tmp_path, "d.md", "x\n")
    assert run_main("check_docs", [doc, "--kb", KB, "--answers", path], capsys)[0] == 2


def test_select_without_template_sections_falls_back_with_a_warning(tmp_path, capsys):
    kb = tmp_path / "kb"
    shutil.copytree(KB, kb)
    fm = json.loads((kb / "feature-map.json").read_text(encoding="utf-8"))
    del fm["templates"], fm["documents"]
    (kb / "feature-map.json").write_text(json.dumps(fm), encoding="utf-8")
    module = load("select")
    capsys.readouterr()
    code = module.main(["--kb", str(kb), "--today", TODAY, "--features", "analytics.web_counter", "--subject", "ul"])
    captured = capsys.readouterr()
    out = json.loads(captured.out)
    assert code == 0
    assert out["templates"] == ["tpl-banner", "tpl-policy"]  # the requirements' own template lists
    assert [d["path"] for d in out["documents"]] == ["documents/doc-analytics.md"]  # ids named in the spec
    assert any('"templates"' in w for w in out["warnings"])
    assert "no \"templates\"" in captured.err


def test_select_warns_about_unknown_feature_and_sector(capsys):
    code, out = run_json("select", select_args("--features", "no.such.feature", "--sectors", "mining"), capsys)
    assert code == 0
    text = " ".join(out["warnings"])
    assert "no.such.feature" in text and "mining" in text


def test_select_unknown_requirement_in_map_is_a_warning(tmp_path, capsys):
    kb = tmp_path / "kb"
    shutil.copytree(KB, kb)
    fm = json.loads((kb / "feature-map.json").read_text(encoding="utf-8"))
    fm["always"].append("ru:ghost")
    (kb / "feature-map.json").write_text(json.dumps(fm), encoding="utf-8")
    code, out = run_json("select", ["--kb", kb, "--today", TODAY], capsys)
    assert code == 0 and "ru:ghost" not in ids(out["applicable"])
    assert any("ru:ghost" in w for w in out["warnings"])


def test_select_bad_input_exits_2(capsys, tmp_path):
    assert run_main("select", select_args("--subject", "alien"), capsys)[0] == 2
    assert run_main("select", select_args("--models", "b2x"), capsys)[0] == 2
    assert run_main("select", select_args("--products", "tv"), capsys)[0] == 2
    assert run_main("select", ["--kb", KB, "--today", "18.10.2026"], capsys)[0] == 2
    assert run_main("select", ["--kb", tmp_path / "nope"], capsys)[0] == 2
    assert run_main("select", select_args("--answers", tmp_path / "missing.json"), capsys)[0] == 2


def test_select_cli_is_deterministic():
    args = ["--kb", KB, "--today", TODAY, "--features", "analytics.web_counter,ads.future", "--subject", "ul"]
    first = run_cli("select", *args)
    second = run_cli("select", *args)
    assert first.returncode == 0 and first.stdout == second.stdout


# --------------------------------------------------------------------------
# scan_repo.py
# --------------------------------------------------------------------------

@pytest.fixture()
def repo(tmp_path):
    target = tmp_path / "repo"
    shutil.copytree(FIX / "repo", target)
    # directories that must be skipped, files that must not be scanned
    (target / "node_modules" / "pkg").mkdir(parents=True)
    (target / "node_modules" / "pkg" / "index.js").write_text("ym(1, 'init');\n", encoding="utf-8")
    (target / "build").mkdir()
    (target / "build" / "bundle.js").write_text("ym(2, 'init');\n", encoding="utf-8")
    (target / ".legal").mkdir()
    (target / ".legal" / "privacy.md").write_text("# Политика\nym(3)\n", encoding="utf-8")
    (target / "big.js").write_text("ym(4);\n" + "x" * (1024 * 1024 + 10), encoding="utf-8")
    (target / "blob.bin").write_bytes(b"\x00\x01ym(5)\x00")
    (target / "docs").mkdir()
    (target / "docs" / "guide.md").write_text("The counter is ym(6) in the docs folder.\n", encoding="utf-8")
    (target / "secrets").mkdir()
    (target / "secrets" / "keys.json").write_text('{"counter": "ym(7)"}\n', encoding="utf-8")
    (target / "server.pem").write_text("ym(8)\n", encoding="utf-8")
    (target / ".env").write_text("COUNTER=ym(9)\n", encoding="utf-8")
    (target / "vendor_lib.js").write_text("var a=1;" * 4000 + "ym(10);", encoding="utf-8")  # minified-looking
    (target / "school.py").write_text("# есть лицензия на образовательную деятельность\n", encoding="utf-8")
    (target / "public" / "school.html").write_text("<p>есть лицензия на образовательную деятельность</p>\n",
                                                   encoding="utf-8")
    return target


def scan_repo(path, capsys, *extra, catalog=CATALOG):
    code, out = run_json("scan_repo", [path, "--catalog", catalog, *extra], capsys)
    assert code == 0, out
    return out


def feature_by_id(out):
    return {f["id"]: f for f in out["features"]}


def test_scan_repo_features_and_evidence(repo, capsys):
    out = scan_repo(repo, capsys)
    features = feature_by_id(out)
    assert "analytics.web_counter" in features
    evidence = features["analytics.web_counter"]["evidence"]
    assert {"file": "package.json", "line": 6, "match": "react-yandex-metrika"} in evidence
    assert {"file": "components/Metrika.tsx", "line": 7, "match": "ym("} in evidence
    assert any(e["file"] == "components/Metrika.tsx" and e["match"] == "mc.yandex.ru" for e in evidence)
    assert evidence == sorted(evidence, key=lambda e: (e["file"], e["line"], e["match"]))
    telegram = features["auth.telegram_login"]["evidence"]
    assert any(e["file"] == "public/contacts.html" and e["line"] == 16 for e in telegram)
    assert "analytics.app_sdk" not in features


def test_scan_repo_skips_vendor_build_big_binary_and_legal_dir(repo, capsys):
    out = scan_repo(repo, capsys)
    files = {e["file"] for f in out["features"] for e in f["evidence"]}
    assert not any(name.startswith(("node_modules", "build", ".legal", "secrets", "docs")) for name in files)
    assert not files & {"big.js", "blob.bin", "server.pem", ".env", "vendor_lib.js"}
    assert out["stats"]["skipped_large"] >= 1
    assert not any(p["file"].startswith(".legal") for p in out["legal_pages"])


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_scan_repo_never_opens_a_fifo(repo, capsys):
    os.mkfifo(repo / "pipe.js")  # opening it for reading would block forever
    os.mkfifo(repo / "pipe.html")
    started = time.monotonic()
    out = scan_repo(repo, capsys)
    assert time.monotonic() - started < 20
    assert out["stats"]["files_seen"] == len({p.relative_to(repo).as_posix() for p in repo.rglob("*")
                                              if p.is_file() and not any(
                                                  part in ("node_modules", "build", ".legal", "secrets")
                                                  for part in p.relative_to(repo).parts)})


def test_scan_repo_caps_a_form_block(tmp_path, capsys):
    root = tmp_path / "caps"
    root.mkdir()
    filler = "<p>" + "x" * 7000 + "</p>"
    (root / "late.html").write_text(
        '<form action="/a"><input name="early">' + filler +
        '<label><input type="checkbox" name="agree" checked> Согласен</label></form>', encoding="utf-8")
    (root / "early.html").write_text(
        '<form action="/a"><label><input type="checkbox" name="agree" checked> Согласен</label>' + filler +
        '<input name="late"></form>', encoding="utf-8")
    forms = {f["file"]: f for f in scan_repo(root, capsys)["forms"]}
    # a block ends 6000 characters after <form>: the checkbox past the cap is not seen, the field past it neither
    assert forms["late.html"]["fields"] == ["early"] and forms["late.html"]["has_consent_checkbox"] is False
    assert forms["early.html"]["fields"] == [] and forms["early.html"]["prechecked"] is True


def test_scan_repo_unclosed_forms_do_not_pile_up(tmp_path, capsys):
    root = tmp_path / "unclosed"
    root.mkdir()
    (root / "many.html").write_text('<form action="/a"><input name="a">' * 30000, encoding="utf-8")
    started = time.monotonic()
    forms = scan_repo(root, capsys)["forms"]
    assert time.monotonic() - started < 10
    assert len(forms) == 30000 and {tuple(f["fields"]) for f in forms} == {("a",)}  # each ends at the next opener


def test_scan_repo_invalid_catalog_regex_is_a_warning(repo, capsys):
    out = scan_repo(repo, capsys)
    assert any("payments.broken_regex" in w for w in out["warnings"])


def test_scan_repo_stacks(repo, capsys):
    out = scan_repo(repo, capsys)
    assert out["stacks"] == ["nextjs"]  # ids of references/stacks/<id>.md
    assert "react" in out["frameworks"]
    assert scan_repo(FIX / "repo_flutter", capsys)["stacks"] == ["flutter"]


def test_scan_repo_legal_pages(repo, capsys):
    pages = {(p["file"], p["kind"]) for p in scan_repo(repo, capsys)["legal_pages"]}
    assert ("app/privacy/page.tsx", "privacy") in pages
    assert ("app/offer/page.tsx", "offer") in pages
    assert ("public/contacts.html", "contacts") in pages
    assert not any(f == "components/Footer.tsx" for f, _ in pages)


def test_scan_repo_forms_and_consent_checkboxes(repo, capsys):
    forms = scan_repo(repo, capsys)["forms"]
    by_file = {}
    for form in forms:
        by_file.setdefault(form["file"], []).append(form)

    contact = by_file["components/ContactForm.tsx"]
    assert len(contact) == 1
    assert contact[0]["line"] == 5
    assert {"name", "phone", "comment"} <= set(contact[0]["fields"])
    assert contact[0]["has_consent_checkbox"] is True
    assert contact[0]["prechecked"] is True  # defaultChecked on the consent checkbox

    html_forms = sorted(by_file["public/contacts.html"], key=lambda f: f["line"])
    assert [f["line"] for f in html_forms] == [5, 10]
    first, second = html_forms
    assert first["fields"] == ["email"] and first["has_consent_checkbox"] and first["prechecked"] is True
    # second form: consent checkbox is unchecked; the checked 'remember' box is not a consent box
    assert second["has_consent_checkbox"] is True and second["prechecked"] is False
    assert any(c["name"] == "remember" and c["prechecked"] and not c["consent"] for c in second["checkboxes"])


def test_scan_repo_design_inventory(repo, capsys):
    design = scan_repo(repo, capsys)["design"]
    assert {"tailwind", "radix", "shadcn"} <= set(design["ui_libs"])
    assert "tailwind.config.ts" in design["tokens"]
    assert design["i18n"]["lib"] == "next-intl"
    assert design["i18n"]["catalogs"] == ["messages/ru.json"]
    assert "components/Footer.tsx" in design["footer"]
    assert "components/ui/checkbox.tsx" in design["checkbox"]
    assert "app/layout.tsx" in design["layout"]
    assert "next-app-router" in design["routes"]["convention"]


def test_scan_repo_flutter(capsys):
    out = scan_repo(FIX / "repo_flutter", capsys)
    assert "flutter" in out["stacks"]
    evidence = feature_by_id(out)["analytics.app_sdk"]["evidence"]
    assert {"file": "pubspec.yaml", "line": 5, "match": "appmetrica_plugin"} in evidence
    assert {"file": "lib/main.dart", "line": 4, "match": "AppMetrica.activate"} in evidence
    [form] = out["forms"]
    assert form["file"] == "lib/features/booking/booking_page.dart"
    assert form["fields"] == ["Имя", "Телефон"]
    assert form["has_consent_checkbox"] is True and form["prechecked"] is True
    assert "flutter-material" in out["design"]["ui_libs"]
    assert out["design"]["i18n"]["lib"] == "intl"
    assert "lib/l10n/app_ru.arb" in out["design"]["i18n"]["catalogs"]
    assert "flutter-go_router" in out["design"]["routes"]["convention"]


def test_scan_repo_output_is_deterministic(repo):
    first = run_cli("scan_repo", repo, "--catalog", CATALOG)
    second = run_cli("scan_repo", repo, "--catalog", CATALOG)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["root"] == str(repo)


def test_scan_repo_bad_input_exits_2(tmp_path, capsys):
    assert run_main("scan_repo", [tmp_path / "missing", "--catalog", CATALOG], capsys)[0] == 2
    assert run_main("scan_repo", [FIX / "repo", "--catalog", tmp_path / "nope.json"], capsys)[0] == 2


def test_scan_repo_default_catalog_path_is_next_to_references():
    module = load("scan_repo")
    expected = SCRIPTS.parent / "references" / "features" / "catalog.json"
    assert Path(module.DEFAULT_CATALOG).resolve() == expected.resolve()


# --------------------------------------------------------------------------
# scan_url.py (local server)
# --------------------------------------------------------------------------

class SiteHandler(http.server.SimpleHTTPRequestHandler):
    posts = []
    gets = []
    extra_cookie = None

    def end_headers(self):
        self.send_header("Set-Cookie", "sid=secret-session-value; Path=/; HttpOnly; SameSite=Lax")
        self.send_header("Set-Cookie", "_ym_uid=777; Max-Age=31536000; Domain=.example.test; Secure")
        super().end_headers()

    def do_GET(self):
        SiteHandler.gets.append(self.path)
        if self.path == "/hop":  # same-site redirect that sets a cookie of its own
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", "hop=1; Path=/")
            self.end_headers()
            return
        if self.path == "/slow":
            time.sleep(0.4)
        if self.path == "/redir-off":
            self.send_response(302)
            self.send_header("Location", "https://elsewhere.example/landing")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self):
        SiteHandler.posts.append(self.path)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    directory = tmp_path_factory.mktemp("site")
    shutil.copytree(FIX / "site", directory, dirs_exist_ok=True)
    handler = functools.partial(SiteHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    sitemap = directory / "sitemap.xml"
    sitemap.write_text(sitemap.read_text(encoding="utf-8").replace("{BASE}", base), encoding="utf-8")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    SiteHandler.posts.clear()
    SiteHandler.gets.clear()
    yield base
    server.shutdown()
    server.server_close()


@pytest.fixture(scope="module")
def scanned(site):
    result = run_cli("scan_url", site + "/", "--delay", "0", "--timeout", "5", "--catalog", CATALOG)
    assert result.returncode == 0, result.stderr
    return site, json.loads(result.stdout), result.stdout


def test_scan_url_crawls_same_origin_and_sitemap(scanned):
    base, out, _ = scanned
    urls = {p["url"] for p in out["pages"]}
    assert {base + "/", base + "/catalog.html", base + "/privacy.html", base + "/oferta.html",
            base + "/refund.html", base + "/hidden.html"} <= urls
    assert not any("elsewhere.example" in u or "other-site.example" in u for u in urls)
    assert all(p["status"] == 200 for p in out["pages"])
    assert out["js_executed"] is False
    assert out["origin"] == base
    assert out["sitemap"]["found"] is True and base + "/hidden.html" in out["sitemap"]["urls"]
    sitemap = out["sitemap"]["urls"]
    assert len(sitemap) == len(set(sitemap)) == out["sitemap"]["total"]  # duplicate <loc> entries are listed once


def test_scan_url_never_submits_a_form_and_ignores_page_instructions(scanned):
    _, out, raw = scanned
    assert SiteHandler.posts == []
    paths = {path.split("?")[0] for path in SiteHandler.gets}
    # the page declares a POST form (/send), a GET form (/search) and talks about /steal: none is requested
    assert not paths & {"/send", "/search", "/steal"}
    assert {f["method"] for f in out["forms"]} == {"get", "post"}
    assert "/steal" not in raw
    assert {"/", "/privacy.html", "/hidden.html"} <= paths  # links and sitemap entries are plain GETs


def test_scan_url_does_not_follow_offsite_redirects(scanned):
    base, out, _ = scanned
    skipped = {s["url"]: s["reason"] for s in out["skipped"]}
    assert skipped[base + "/redir-off"].startswith("redirect")
    assert not any("elsewhere.example" in p["url"] for p in out["pages"])


def test_scan_url_legal_links(scanned):
    base, out, _ = scanned
    links = {(l["kind"], l["url"]): l for l in out["legal_links"]}
    assert links[("privacy", base + "/privacy.html")]["in_footer"] is True
    assert ("offer", base + "/oferta.html") in links
    assert ("refund", base + "/refund.html") in links
    assert links[("privacy", base + "/privacy.html")]["found_on"]


def test_scan_url_third_party_hosts(scanned):
    _, out, _ = scanned
    third = out["third_party"]
    assert "mc.yandex.ru" in third["script"]
    assert "www.youtube.com" in third["iframe"]
    assert "top-fwz1.mail.ru" in third["img"]
    assert "fonts.googleapis.com" in third["link"]
    assert "cdn.example-stats.net" in out["inline_script_hosts"]
    assert not any(h.startswith("127.0.0.1") for kind in third.values() for h in kind)


def test_scan_url_forms_with_checkboxes(scanned):
    base, out, _ = scanned
    forms = {f["action"]: f for f in out["forms"]}
    send = forms[base + "/send"]
    assert send["method"] == "post" and send["page"] == base + "/"
    assert send["fields"] == ["name", "phone"]
    assert send["has_consent_checkbox"] is True and send["prechecked"] is True
    by_name = {c["name"]: c for c in send["checkboxes"]}
    assert by_name["agree"]["consent"] is True and by_name["agree"]["prechecked"] is True
    assert by_name["news"]["consent"] is False and by_name["news"]["prechecked"] is False
    search = forms[base + "/search"]
    assert search["method"] == "get" and search["fields"] == ["q"] and search["has_consent_checkbox"] is False


def test_scan_url_set_cookie_of_first_response_without_values(scanned):
    _, out, raw = scanned
    cookies = {c["name"]: c for c in out["cookies"]}
    assert cookies["sid"]["httponly"] is True and cookies["sid"]["samesite"] == "Lax" and cookies["sid"]["secure"] is False
    assert cookies["_ym_uid"]["secure"] is True and cookies["_ym_uid"]["max_age"] == 31536000
    assert cookies["_ym_uid"]["domain"] == ".example.test"
    assert "secret-session-value" not in raw


def test_scan_url_max_pages(site):
    result = run_cli("scan_url", site + "/", "--delay", "0", "--max-pages", "2")
    out = json.loads(result.stdout)
    assert result.returncode == 0 and len(out["pages"]) == 2


def test_scan_url_collects_set_cookie_along_the_same_site_redirect_chain(site):
    result = run_cli("scan_url", site + "/hop", "--delay", "0", "--max-pages", "1")
    out = json.loads(result.stdout)
    assert result.returncode == 0
    names = [c["name"] for c in out["cookies"]]
    assert "hop" in names and "sid" in names and names.count("sid") == 1  # identical cookies listed once
    assert out["pages"][0]["url"] == site + "/"


def test_scan_url_deadline_stops_the_scan(site):
    result = run_cli("scan_url", site + "/", "--delay", "0.3", "--deadline", "0.5")
    out = json.loads(result.stdout)
    assert result.returncode == 0 and out["deadline_reached"] is True
    assert len(out["pages"]) < 6 and any("deadline" in e["error"] for e in out["errors"])
    assert run_cli("scan_url", site + "/", "--deadline", "0").returncode == 2
    assert json.loads(run_cli("scan_url", site + "/", "--delay", "0", "--max-pages", "2").stdout)[
        "deadline_reached"] is False


def test_scan_url_overlong_tag_is_replaced_not_truncated_on_the_python_39_path():
    module = load("scan_url")
    page = ('<img src="data:image/png;base64,' + "A" * 6000 + '"><footer><a href="/privacy">Политика</a>'
            '<a href="/offer">Оферта</a></footer>')
    prepared = module.prepare_html(page, force=True)  # force: the < 3.10 path on any interpreter
    assert prepared == '<x><footer><a href="/privacy">Политика</a><a href="/offer">Оферта</a></footer>'
    parser = module.PageParser("http://example.test/")
    parser.feed(prepared)
    parser.close()
    assert [(link["href"], link["in_footer"]) for link in parser.links] == [("/privacy", True), ("/offer", True)]
    # a tag that never reaches '>' is replaced as a whole too, and short tags are untouched
    assert module.prepare_html("<a " * 8000, force=True) == "<x"
    assert module.prepare_html("<a " * 8000 + "<p>x</p>", force=True) == "<x>x</p>"  # ends at the next '>'
    assert module.prepare_html('<a href="/x">y</a>' * 50, force=True) == '<a href="/x">y</a>' * 50


def test_scan_url_malformed_markup_is_cut_and_parsed_fast():
    module = load("scan_url")
    html = "<a " * 8000
    cut = module.prepare_html(html, force=True)
    assert len(cut) <= 4096 + len("<a ")  # one run of 24000 characters without '>' is replaced
    assert module.prepare_html("<p>ok</p>" * 100, force=True) == "<p>ok</p>" * 100
    started = time.monotonic()
    parser = module.PageParser("http://example.test/")
    parser.feed(module.prepare_html(html))
    parser.close()
    assert time.monotonic() - started < 2
    assert module.DEFAULT_MAX_BYTES == 1024 * 1024


def test_scan_url_unreachable_and_bad_input():
    free = socket.socket()
    free.bind(("127.0.0.1", 0))
    port = free.getsockname()[1]
    free.close()
    result = run_cli("scan_url", f"http://127.0.0.1:{port}/", "--delay", "0", "--timeout", "2")
    assert result.returncode == 1
    assert json.loads(result.stdout)["error"]
    assert run_cli("scan_url", "ftp://example.test/").returncode == 2
    assert run_cli("scan_url", "not-a-url").returncode == 2


# --------------------------------------------------------------------------
# registry.py
# --------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.status = status
        self.headers = headers or {}

    def read(self, *args):
        return self._body

    def getcode(self):
        return self.status

    def geturl(self):
        return ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeUrlopen:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout=None, **kwargs):
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture()
def registry(monkeypatch):
    module = load("registry")
    monkeypatch.delenv("LEGAL_KIT_OFFLINE", raising=False)
    monkeypatch.delenv("LEGAL_KIT_STUBS", raising=False)
    monkeypatch.setattr(module, "pause", lambda seconds: None, raising=False)
    return module


def lookup(registry, capsys, kind, arg, *extra):
    capsys.readouterr()
    code = registry.main([kind, arg, *extra])
    return code, json.loads(capsys.readouterr().out)


def test_registry_offline_stub_is_returned(registry, tmp_path, monkeypatch, capsys):
    stub = {"_comment": "fictitious", "status": "ok", "data": {"inn": "0012345017", "name": "ООО Тест"},
            "url": "https://egrul.nalog.ru/", "checked_at": "2026-10-18T09:00:00Z"}
    (tmp_path / "egrul-0012345017.json").write_text(json.dumps(stub, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("LEGAL_KIT_OFFLINE", "1")
    monkeypatch.setenv("LEGAL_KIT_STUBS", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen())  # any network call would pop from an empty list
    code, out = lookup(registry, capsys, "egrul", "0012345017")
    assert code == 0
    assert out["status"] == "ok" and out["data"]["name"] == "ООО Тест"
    assert out["url"] == "https://egrul.nalog.ru/" and out["checked_at"] == "2026-10-18T09:00:00Z"
    assert "_comment" not in out


def test_registry_offline_missing_stub_is_an_error(registry, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LEGAL_KIT_OFFLINE", "1")
    monkeypatch.setenv("LEGAL_KIT_STUBS", str(tmp_path))
    code, out = lookup(registry, capsys, "egrul", "0012345017")
    assert code == 1 and out["status"] == "error" and "egrul-0012345017.json" in out["note"]


def test_registry_rkn_is_manual_with_instructions(registry, capsys):
    code, out = lookup(registry, capsys, "rkn", "0012345017")
    assert code == 0 and out["status"] == "manual"
    assert out["url"] == "https://pd.rkn.gov.ru/operators-registry/operators-list/"
    assert "0012345017" in out["note"] and "Russian" in out["note"]


def test_registry_rkn_uses_stub_when_offline(registry, tmp_path, monkeypatch, capsys):
    stub = {"status": "manual", "data": {"reason": "geo-block"}, "url": "https://pd.rkn.gov.ru/x", "checked_at": "2026-10-18T09:00:00Z"}
    (tmp_path / "rkn-0012345017.json").write_text(json.dumps(stub), encoding="utf-8")
    monkeypatch.setenv("LEGAL_KIT_OFFLINE", "1")
    monkeypatch.setenv("LEGAL_KIT_STUBS", str(tmp_path))
    _, out = lookup(registry, capsys, "rkn", "0012345017")
    assert out["data"] == {"reason": "geo-block"} and out["url"] == "https://pd.rkn.gov.ru/x"
    # offline without a stub: the default manual answer, still no network
    monkeypatch.setenv("LEGAL_KIT_STUBS", str(tmp_path / "empty"))
    _, default = lookup(registry, capsys, "rkn", "0098765437")
    assert default["status"] == "manual" and "0098765437" in default["note"]


def test_registry_egrul_flow(registry, monkeypatch, capsys):
    row = {"n": 'ООО "ТЕСТ"', "i": "0098765437", "o": "1020000000008", "k": "ul", "r": "04.03.2002", "t": "rowtoken"}
    fake = FakeUrlopen(FakeResponse(json.dumps({"t": "tok", "captchaRequired": False})),
                       FakeResponse(json.dumps({"rows": [row]})))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    code, out = lookup(registry, capsys, "egrul", "0098765437")
    assert code == 0 and out["status"] == "ok"
    assert out["data"]["name"] == 'ООО "ТЕСТ"' and out["data"]["inn"] == "0098765437"
    assert out["data"]["ogrn"] == "1020000000008" and out["data"]["registered"] == "2002-03-04"
    assert out["url"] == "https://egrul.nalog.ru/" and out["checked_at"].endswith("Z")
    first, second = fake.requests
    assert first.full_url == "https://egrul.nalog.ru/" and first.get_method() == "POST"
    assert first.data == b"query=0098765437&region=&page=&vyp3CaptchaToken="
    assert second.full_url == "https://egrul.nalog.ru/search-result/tok"


def test_registry_egrul_not_found(registry, monkeypatch, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(
        FakeResponse(json.dumps({"t": "tok", "captchaRequired": False})), FakeResponse(json.dumps({"rows": []}))))
    code, out = lookup(registry, capsys, "egrul", "0098765437")
    assert code == 0 and out["status"] == "not_found"


def test_registry_egrul_captcha_is_manual(registry, monkeypatch, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(
        FakeResponse(json.dumps({"t": "tok", "captchaRequired": True}))))
    code, out = lookup(registry, capsys, "egrul", "0098765437")
    assert code == 0 and out["status"] == "manual"
    assert out["url"] == "https://egrul.nalog.ru/" and "0098765437" in out["note"]
    assert "captcha" in out["note"].lower()


@pytest.mark.parametrize("failure", [
    urllib.error.HTTPError("https://egrul.nalog.ru/", 403, "Forbidden", {}, None),
    urllib.error.URLError(socket.timeout("timed out")),
    socket.timeout("timed out"),
])
def test_registry_blocked_or_timeout_is_manual(registry, monkeypatch, capsys, failure):
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(failure))
    code, out = lookup(registry, capsys, "egrul", "0098765437")
    assert code == 0 and out["status"] == "manual" and out["note"] and out["url"]


def test_registry_egrul_error_status_with_a_captcha_page_is_manual(registry, monkeypatch, capsys):
    for code in (400, 403, 500, 503):
        captcha = urllib.error.HTTPError("u", code, "x", {}, io.BytesIO("<html>Введите капчу</html><!-- captcha -->".encode()))
        monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(captcha))
        exit_code, out = lookup(registry, capsys, "egrul", "0098765437")
        assert exit_code == 0 and out["status"] == "manual" and "Подождите минуту" in out["note"], code
    second_step = urllib.error.HTTPError("u", 500, "x", {}, io.BytesIO(b"<html>captcha</html>"))
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(
        FakeResponse(json.dumps({"t": "tok", "captchaRequired": False})), second_step))
    assert lookup(registry, capsys, "egrul", "0098765437")[1]["status"] == "manual"
    plain_gateway = urllib.error.HTTPError("u", 502, "x", {}, io.BytesIO(b"<html>Bad Gateway</html>"))
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(plain_gateway))
    exit_code, out = lookup(registry, capsys, "egrul", "0098765437")
    assert exit_code == 1 and out["status"] == "error"  # an ordinary error page stays an error


def test_registry_html_captcha_page_is_manual(registry, monkeypatch, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(FakeResponse("<html>Введите капчу (captcha)</html>")))
    _, out = lookup(registry, capsys, "egrul", "0098765437")
    assert out["status"] == "manual"


def test_registry_server_error_is_error(registry, monkeypatch, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(
        urllib.error.HTTPError("https://egrul.nalog.ru/", 502, "Bad Gateway", {}, None)))
    code, out = lookup(registry, capsys, "egrul", "0098765437")
    assert code == 1 and out["status"] == "error"


def test_registry_npd_ok_and_not_npd(registry, monkeypatch, capsys):
    fake = FakeUrlopen(FakeResponse(json.dumps({"status": True, "message": "Является плательщиком"})))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    code, out = lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")
    assert code == 0 and out["status"] == "ok"
    assert out["data"] == {"inn": "009876543299", "date": "2026-10-01", "is_npd": True,
                           "message": "Является плательщиком"}
    request = fake.requests[0]
    assert request.full_url == "https://statusnpd.nalog.ru/api/v1/tracker/taxpayer_status"
    assert json.loads(request.data) == {"inn": "009876543299", "requestDate": "2026-10-01"}
    assert request.get_header("Content-type") == "application/json"

    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(FakeResponse(json.dumps({"status": False, "message": "нет"}))))
    code, out = lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")
    assert out["status"] == "not_found" and out["data"]["is_npd"] is False


def test_registry_npd_has_no_in_process_throttle(registry, monkeypatch, capsys):
    fake = FakeUrlopen(FakeResponse(json.dumps({"status": True, "message": "ok"})),
                       FakeResponse(json.dumps({"status": True, "message": "ok"})))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")[1]["status"] == "ok"
    assert lookup(registry, capsys, "npd", "001357924634", "--date", "2026-10-01")[1]["status"] == "ok"
    assert len(fake.requests) == 2 and not hasattr(registry, "reset_throttle")


def test_registry_npd_limit_captcha_and_html_are_manual(registry, monkeypatch, capsys):
    limited = urllib.error.HTTPError("u", 422, "x", {}, io.BytesIO(json.dumps(
        {"code": "taxpayer.status.service.limited.error", "message": "limit"}).encode()))
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(limited))
    code, out = lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")
    assert code == 0 and out["status"] == "manual"
    assert "Подождите минуту и повторите / проверьте вручную по ссылке: https://npd.nalog.ru/check-status/" in out["note"]
    assert "at most 2 requests per minute" in out["note"] and out["url"] == "https://npd.nalog.ru/check-status/"
    for body in ("<html><body>Проверка: captcha</body></html>", "<!doctype html><title>Доступ ограничен</title>"):
        monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(FakeResponse(body)))
        _, out = lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")
        assert out["status"] == "manual" and "Подождите минуту" in out["note"], body
    html_error = urllib.error.HTTPError("u", 400, "x", {}, io.BytesIO(b"<html>captcha</html>"))
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(html_error))
    assert lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")[1]["status"] == "manual"


def test_registry_npd_unavailable_is_manual_and_other_rejections_are_errors(registry, monkeypatch, capsys):
    unavailable = urllib.error.HTTPError("u", 503, "x", {}, io.BytesIO(json.dumps(
        {"code": "taxpayer.status.service.unavailable.error"}).encode()))
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(unavailable))
    _, out = lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")
    assert out["status"] == "manual" and "npd.nalog.ru/check-status" in out["url"]
    invalid = urllib.error.HTTPError("u", 422, "x", {}, io.BytesIO(json.dumps({"code": "validation.failed"}).encode()))
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(invalid))
    code, out = lookup(registry, capsys, "npd", "009876543299", "--date", "2026-10-01")
    assert code == 1 and out["status"] == "error"


def test_registry_egrul_search_result_captcha_or_html_is_manual(registry, monkeypatch, capsys):
    start = FakeResponse(json.dumps({"t": "tok", "captchaRequired": False}))
    for second in (FakeResponse("<html>captcha</html>"), FakeResponse(json.dumps({"captchaRequired": True}))):
        monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(start, second))
        _, out = lookup(registry, capsys, "egrul", "0098765437")
        assert out["status"] == "manual" and "Подождите минуту" in out["note"]
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(FakeResponse("<!doctype html><title>x</title>")))
    assert lookup(registry, capsys, "egrul", "0098765437")[1]["status"] == "manual"


class FakeSocket:
    def __init__(self, reply):
        self.sent = b""
        self.chunks = [reply, b""]

    def sendall(self, data):
        self.sent += data

    def recv(self, size):
        return self.chunks.pop(0)

    def settimeout(self, value):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


WHOIS_REPLY = (
    "% TCI Whois Service\ndomain:        EXAMPLE-TEST.RU\nnserver:       ns1.example.test.\nnserver:       ns2.example.test.\n"
    "state:         REGISTERED, DELEGATED, VERIFIED\norg:           Test Org\nregistrar:     TEST-RU\n"
    "created:       2022-05-25T10:40:44Z\npaid-till:     2027-05-25T10:40:44Z\nsource:        TCI\n"
)


def test_registry_whois_parses_reply(registry, monkeypatch, capsys):
    sock = FakeSocket(WHOIS_REPLY.encode("utf-8"))
    calls = []
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout=None: calls.append(address) or sock)
    code, out = lookup(registry, capsys, "whois", "Example-Test.RU")
    assert code == 0 and out["status"] == "ok"
    assert calls == [("whois.tcinet.ru", 43)] and sock.sent == b"example-test.ru\r\n"
    data = out["data"]
    assert data["registrar"] == "TEST-RU" and data["created"] == "2022-05-25" and data["paid-till"] == "2027-05-25"
    assert data["state"] == "REGISTERED, DELEGATED, VERIFIED"
    assert data["nserver"] == ["ns1.example.test.", "ns2.example.test."]
    assert out["url"] == "whois.tcinet.ru:43"


def test_registry_whois_punycode_and_not_found(registry, monkeypatch, capsys):
    sock = FakeSocket(b"No entries found for the selected source(s).\n")
    monkeypatch.setattr(socket, "create_connection", lambda address, timeout=None: sock)
    code, out = lookup(registry, capsys, "whois", "пример.рф")
    assert code == 0 and out["status"] == "not_found"
    assert sock.sent == b"xn--e1afmkfd.xn--p1ai\r\n"


def test_registry_whois_timeout_is_manual_and_refusal_is_error(registry, monkeypatch, capsys):
    def timeout(address, timeout=None):
        raise socket.timeout("timed out")

    monkeypatch.setattr(socket, "create_connection", timeout)
    code, out = lookup(registry, capsys, "whois", "example-test.ru")
    assert code == 0 and out["status"] == "manual" and out["note"]

    def refused(address, timeout=None):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(socket, "create_connection", refused)
    code, out = lookup(registry, capsys, "whois", "example-test.ru")
    assert code == 1 and out["status"] == "error"


CBR_PAGE = "<html><head><title>Банк России</title></head><body><h1>ООО «Тест-Финанс»</h1><p>ОГРН 1020000000008</p></body></html>"


def test_registry_cbr_minimal_parsing(registry, monkeypatch, capsys):
    fake = FakeUrlopen(FakeResponse(CBR_PAGE))
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    code, out = lookup(registry, capsys, "cbr", "1020000000008")
    assert code == 0 and out["status"] == "ok"
    assert out["data"]["ogrn"] == "1020000000008" and out["data"]["name"] == "ООО «Тест-Финанс»"
    assert fake.requests[0].full_url == "https://www.cbr.ru/finorg/foinfo/?ogrn=1020000000008"
    assert out["url"] == "https://www.cbr.ru/finorg/foinfo/?ogrn=1020000000008"


def test_registry_cbr_not_found_and_unreliable_page(registry, monkeypatch, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(FakeResponse("<html><body>Информация не найдена</body></html>")))
    assert lookup(registry, capsys, "cbr", "1020000000008")[1]["status"] == "not_found"
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(FakeResponse("<html><body>???</body></html>")))
    _, out = lookup(registry, capsys, "cbr", "1020000000008")
    assert out["status"] == "manual" and "cbr.ru/finorg" in out["url"]
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(urllib.error.HTTPError("u", 404, "x", {}, None)))
    assert lookup(registry, capsys, "cbr", "1020000000008")[1]["status"] == "not_found"
    # "not found" wins over an echoed OGRN (a search page that repeats the query)
    echoed = "<html><body><input value='1020000000008'>Запрос 1020000000008: информация не найдена</body></html>"
    monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(FakeResponse(echoed)))
    assert lookup(registry, capsys, "cbr", "1020000000008")[1]["status"] == "not_found"
    # other HTTP and network failures of the Bank of Russia site are manual (registries.md), not error
    for failure in (urllib.error.HTTPError("u", 500, "x", {}, io.BytesIO(b"")), urllib.error.URLError("dns failure")):
        monkeypatch.setattr(urllib.request, "urlopen", FakeUrlopen(failure))
        code, out = lookup(registry, capsys, "cbr", "1020000000008")
        assert code == 0 and out["status"] == "manual" and "cbr.ru/finorg" in out["url"]


def test_registry_bad_input_exits_2(registry, capsys):
    for argv in (["egrul", "123"], ["egrul", INN10_BAD], ["egrul", "abc"], ["npd", INN10_OK[0]],
                 ["npd", INN12_OK[0], "--date", "01.10.2026"], ["whois", "no spaces.ru"], ["whois", "../etc"],
                 ["cbr", OGRN13_BAD], ["rkn", "12"], ["bogus", "x"]):
        capsys.readouterr()
        with contextlib.suppress(SystemExit):
            code = registry.main(argv)
            assert code == 2, argv


def test_registry_cli_offline_with_stub(tmp_path):
    stub = {"_comment": "x", "status": "ok", "data": {"inn": "0012345017"}, "url": "https://egrul.nalog.ru/",
            "checked_at": "2026-10-18T09:00:00Z"}
    (tmp_path / "egrul-0012345017.json").write_text(json.dumps(stub), encoding="utf-8")
    result = run_cli("registry", "egrul", "0012345017", env={"LEGAL_KIT_OFFLINE": "1", "LEGAL_KIT_STUBS": str(tmp_path)})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["data"] == {"inn": "0012345017"}


# --------------------------------------------------------------------------
# check_docs.py
# --------------------------------------------------------------------------

def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def check(capsys, files, *extra, answers=ANSWERS):
    argv = [*files, "--kb", KB, *extra]
    if answers is not None:
        argv += ["--answers", answers]
    code, out = run_json("check_docs", argv, capsys)
    return code, out["issues"]


def kinds(issues):
    return sorted(i["kind"] for i in issues)


def test_check_docs_clean_document(tmp_path, capsys):
    path = write(tmp_path, "policy.md", "# Политика\n\nОператор: ООО «Тест-Компания», ИНН 0098765437, ОГРН 1020000000008.\n")
    code, issues = check(capsys, [path])
    assert code == 0 and issues == []


def test_check_docs_placeholders_and_conditions(tmp_path, capsys):
    text = (
        "Оператор {{НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА}}, ИНН {{ИНН}}.\n"
        "[если есть оформление заказа:] блок.\n"
        "[Если поставщик использует данные — укажите это.]\n"
        "[вставьте блок 3.2, если нужен]\n"
        "[юридическое лицо:] текст\n"
        "Ссылка [Название:](https://example.test) и [x] пункт — не маркеры.\n"
    )
    path = write(tmp_path, "doc.md", text)
    code, issues = check(capsys, [path])
    assert code == 1
    placeholders = [i for i in issues if i["kind"].startswith("placeholder")]
    assert [(i["line"], i["text"], i["name"]) for i in placeholders] == [
        (1, "{{НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА}}", "НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА"), (1, "{{ИНН}}", "ИНН")]
    conditions = [i for i in issues if i["kind"] == "condition"]
    assert [i["line"] for i in conditions] == [2, 3, 4, 5]
    assert all(i["blocking"] is True for i in conditions)
    assert all(i["file"] == str(path) for i in issues)


def test_check_docs_classifies_placeholders_and_drafts_never_block_on_them(tmp_path, capsys):
    text = ("Оператор {{НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА}}, ИНН {{ИНН}}, ОГРН {{ОГРН_ИЛИ_ОГРНИП}}, тел. {{ТЕЛЕФОН}}.\n"
            "Срок хранения: {{СРОК_ХРАНЕНИЯ}}; БД: {{РЕГИОН_РАЗМЕЩЕНИЯ_БД}}.\n")
    code, out = run_json("check_docs", [write(tmp_path, "draft.md", text), "--kb", KB, "--answers", ANSWERS], capsys)
    issues = out["issues"]
    assert code == 0 and out["blocking"] == 0
    assert [(i["name"], i["kind"]) for i in issues] == [
        ("НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА", "placeholder_requisite"), ("ИНН", "placeholder_requisite"),
        ("ОГРН_ИЛИ_ОГРНИП", "placeholder_requisite"), ("ТЕЛЕФОН", "placeholder_requisite"),
        ("СРОК_ХРАНЕНИЯ", "placeholder_fact"), ("РЕГИОН_РАЗМЕЩЕНИЯ_БД", "placeholder_fact")]
    assert all(i["blocking"] is False for i in issues)
    assert out["summary"] == {"placeholder_requisite": 4, "placeholder_fact": 2}


def answers_with(tmp_path, **owner):
    answers = json.loads(ANSWERS.read_text(encoding="utf-8"))
    answers["owner"].update(owner)
    path = tmp_path / "answers-owner.json"
    path.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    return path


def test_check_docs_public_pages_block_on_placeholders_except_withheld_requisites(tmp_path, capsys):
    page = write(tmp_path, "requisites.html",
                 "<p>ИНН {{ИНН}}, ОГРН {{ОГРН_ИЛИ_ОГРНИП}}</p>\n<p>Режим работы: {{РЕЖИМ_РАБОТЫ}}</p>\n")
    draft = write(tmp_path, "draft.md", "ИНН {{ИНН}}, срок {{СРОК_ХРАНЕНИЯ}}\n")
    answers = answers_with(tmp_path, inn=None, ogrn=None, withheld=["ИНН"])
    code, out = run_json("check_docs", [draft, "--public", page, "--kb", KB, "--answers", answers], capsys)
    assert code == 1 and out["public"] == [str(page)]
    flags = {(i["file"], i["name"]): i["blocking"] for i in out["issues"]}
    assert flags == {(str(page), "ИНН"): False, (str(page), "ОГРН_ИЛИ_ОГРНИП"): True,
                     (str(page), "РЕЖИМ_РАБОТЫ"): True, (str(draft), "ИНН"): False,
                     (str(draft), "СРОК_ХРАНЕНИЯ"): False}
    assert out["blocking"] == 2
    withheld_both = answers_with(tmp_path, inn=None, ogrn=None, withheld=["ИНН", "ОГРН_ИЛИ_ОГРНИП"])
    page_ok = write(tmp_path, "footer.html", "<p>ИНН {{ИНН}}, ОГРН {{ОГРН_ИЛИ_ОГРНИП}}</p>\n")
    code, out = run_json("check_docs", ["--public", page_ok, "--kb", KB, "--answers", withheld_both], capsys)
    assert code == 0 and len(out["issues"]) == 2 and not any(i["blocking"] for i in out["issues"])
    # without answers nothing is withheld
    code, out = run_json("check_docs", ["--public", page_ok, "--kb", KB], capsys)
    assert code == 1 and all(i["blocking"] for i in out["issues"])


def test_check_docs_public_code_ignores_template_syntax_and_slices(tmp_path, capsys):
    tsx = write(tmp_path, "Footer.tsx",
                "export const F = () => <p style={{ color: 'red' }} data-x={{a: 1}}>{t('Legal.title')}</p>;\n")
    html = write(tmp_path, "base.html",
                 '<html lang="{{ LANGUAGE_CODE }}"><p>{{ _(\'Политика\') }}</p><p>{{ form.consent_pd }}</p>\n')
    py = write(tmp_path, "views.py", "name = value[1:]\nother = items[start:]\n")
    code, issues = check(capsys, [], "--public", tsx, "--public", html, "--public", py)
    assert code == 0 and issues == []


def test_check_docs_public_takes_one_file_per_flag(tmp_path, capsys):
    draft = write(tmp_path, "draft.md", "{{СРОК_ХРАНЕНИЯ}}\n")
    page = write(tmp_path, "page.html", "{{СРОК_ХРАНЕНИЯ}}\n")
    # a second file after one --public is refused instead of being taken silently as a draft or a page
    assert run_main("check_docs", [draft, "--public", page, draft, "--kb", KB], capsys)[0] == 2
    # a draft after --public PAGE stays a draft
    code, out = run_json("check_docs", ["--public", page, draft, "--kb", KB], capsys)
    assert code == 1 and out["public"] == [str(page)]
    assert {(Path(i["file"]).name, i["blocking"]) for i in out["issues"]} == {("page.html", True), ("draft.md", False)}
    help_text = run_cli("check_docs", "--help").stdout
    assert "once per file" in help_text and "before" in help_text


def test_check_docs_runtime_placeholders_become_project_interpolation(tmp_path, capsys):
    text = "Здравствуйте, {{ИМЯ_ПОКУПАТЕЛЯ}}! Заказ № {{НОМЕР_ЗАКАЗА}}. Отписаться: {{ССЫЛКА_ОТПИСКИ}}.\n"
    draft = write(tmp_path, "confirm.md", text)
    page = write(tmp_path, "OrderMail.tsx", text)
    code, out = run_json("check_docs", [draft, "--public", page, "--kb", KB, "--answers", ANSWERS], capsys)
    assert code == 1
    kinds_seen = {(Path(i["file"]).name, i["kind"], i["blocking"]) for i in out["issues"]}
    assert kinds_seen == {("confirm.md", "placeholder_runtime", False), ("OrderMail.tsx", "placeholder_runtime", True)}
    assert all("interpolation" in i["message"] for i in out["issues"] if i["blocking"])
    converted = write(tmp_path, "OrderMail2.tsx",
                      "Здравствуйте, {name}! Заказ № ${order.number}. <a href={{ unsubscribe_url }}>Отписаться</a>\n")
    assert check(capsys, [], "--public", converted)[0] == 0


def placeholder_hints():
    pack = json.loads((REAL_KB / "placeholders.json").read_text(encoding="utf-8"))
    return {name: entry.get("hint", "") for name, entry in pack.items()}


def test_check_docs_runtime_names_cover_the_system_filled_hints():
    module = load("check_docs")
    hints = placeholder_hints()
    runtime = module.RUNTIME_PLACEHOLDERS
    assert runtime <= set(hints), sorted(runtime - set(hints))
    assert {name for name, hint in hints.items() if hint.startswith("Подставляются системой")} <= runtime
    assert {"ИМЯ_ПОКУПАТЕЛЯ", "НОМЕР_ЗАКАЗА", "ФИО_ПОЛЬЗОВАТЕЛЯ", "КОНТАКТЫ_ПОЛЬЗОВАТЕЛЯ", "ИМЯ_ПОЛЬЗОВАТЕЛЯ",
            "EMAIL_ПОЛЬЗОВАТЕЛЯ", "ДАТА_СОГЛАСИЯ", "ИСТОЧНИК_СОГЛАСИЯ", "ТЕЛЕФОН_ПОЛЬЗОВАТЕЛЯ", "ДАТА_ЗАКАЗА",
            "СОСТАВ_ЗАКАЗА", "ЦЕНА_ЗАКАЗА"} <= runtime
    assert not runtime & module.REQUISITE_PLACEHOLDERS


# Hints of placeholders.json that describe the owner's requisites; the names under them are requisites except
# the few that are document facts or decisions.
REQUISITE_HINT_PREFIXES = ("Реквизиты по", "Для ИП", "Для юрлица", "Для иностранной компании", "Рабочий ящик")
FACTS_UNDER_REQUISITE_HINTS = {"РЕЖИМ_РАБОТЫ", "РЕКВИЗИТЫ_ИНОСТРАННОГО_ПРОДАВЦА_В_РЕКЛАМЕ", "ССЫЛКА_НА_ФОРМУ_ЗАЯВЛЕНИЙ"}


def test_check_docs_requisite_names_cover_the_requisite_hints():
    names = load("check_docs").REQUISITE_PLACEHOLDERS
    under = {name for name, hint in placeholder_hints().items() if hint.startswith(REQUISITE_HINT_PREFIXES)}
    assert under - FACTS_UNDER_REQUISITE_HINTS <= names, sorted(under - FACTS_UNDER_REQUISITE_HINTS - names)
    assert not FACTS_UNDER_REQUISITE_HINTS & names


def test_check_docs_risk_clauses_are_reported_but_do_not_block(tmp_path, capsys):
    risk_only = write(tmp_path, "oferta.md", "# Публичная оферта\n\n7.1. Возможна «оплата только банковской картой».\n")
    code, out = run_json("check_docs", [risk_only, "--kb", KB], capsys)
    assert code == 0 and [(i["kind"], i["severity"], i["blocking"]) for i in out["issues"]] == [
        ("forbidden_clause", "risk", False)]
    code, out = run_json("check_docs", ["--public", risk_only, "--kb", KB], capsys)
    assert code == 0 and out["blocking"] == 0
    violation = write(tmp_path, "oferta2.md", "# Оферта\n\nПродавец вправе отменить заказ.\n")
    code, out = run_json("check_docs", [violation, "--kb", KB], capsys)
    assert code == 1 and out["issues"][0]["blocking"] is True


def test_check_docs_requisite_names_are_placeholders_of_the_pack():
    names = load("check_docs").REQUISITE_PLACEHOLDERS
    pack = json.loads((REAL_KB / "placeholders.json").read_text(encoding="utf-8"))
    assert {"НАИМЕНОВАНИЕ_ВЛАДЕЛЬЦА", "ИНН", "ОГРН_ИЛИ_ОГРНИП", "АДРЕС", "EMAIL_ДЛЯ_ОБРАЩЕНИЙ", "ТЕЛЕФОН"} <= names
    assert names <= set(pack), sorted(names - set(pack))
    assert "СРОК_ХРАНЕНИЯ" not in names and "РЕЖИМ_РАБОТЫ" not in names


def test_check_docs_bad_withheld_or_no_files_exit_2(tmp_path, capsys):
    doc = write(tmp_path, "d.md", "x\n")
    for bad in ("ИНН", [1], {"ИНН": True}):
        path = answers_with(tmp_path, withheld=bad)
        assert run_main("check_docs", [doc, "--kb", KB, "--answers", path], capsys)[0] == 2, bad
    assert run_main("check_docs", ["--kb", KB], capsys)[0] == 2


def test_check_docs_inn_and_ogrn_checksums(tmp_path, capsys):
    good = ("ИНН " + INN10_OK[0] + ", ИНН: " + INN12_OK[0] + ", ОГРН " + OGRN13_OK[0] + ", ОГРНИП № " + OGRN15_OK[0]
            + ", ИНН/КПП " + INN10_OK[1] + "/770701001.")
    code, issues = check(capsys, [write(tmp_path, "good.md", good)], answers=None)
    assert code == 0 and issues == []
    bad = f"ИНН {INN10_BAD}\nИНН {INN12_BAD}\nОГРН {OGRN13_BAD}\nОГРНИП {OGRN15_BAD}\nИНН 12345\nОГРН 123\n"
    code, issues = check(capsys, [write(tmp_path, "bad.md", bad)], answers=None)
    assert code == 1
    assert [(i["kind"], i["line"]) for i in issues] == [
        ("inn_checksum", 1), ("inn_checksum", 2), ("ogrn_checksum", 3), ("ogrn_checksum", 4),
        ("inn_checksum", 5), ("ogrn_checksum", 6)]


def test_check_docs_accepts_digits_grouped_with_spaces_and_hyphens(tmp_path, capsys):
    grouped = ("ИНН 0098 7654 37, ИНН: 0098\u00a07654\u00a037, ИНН 0098-7654-37, ОГРН 1 02 0000 00000 8, "
               "ОГРНИП 322 0000 0000 0012, ИНН 0013 5792 4634\n")
    assert check(capsys, [write(tmp_path, "g.md", grouped)], answers=None)[1] == []
    wrong = "ИНН 0098 7654 38\nОГРН 1 02 0000 00000 9\n"
    code, issues = check(capsys, [write(tmp_path, "w.md", wrong)], answers=None)
    assert [(i["kind"], i["value"]) for i in issues] == [("inn_checksum", "0098765438"),
                                                          ("ogrn_checksum", "1020000000009")]
    # the grouped number is compared with answers.json after normalising
    _, issues = check(capsys, [write(tmp_path, "m.md", "ООО «Тест-Компания», ИНН 0013 5792 40.\n")])
    assert [i["field"] for i in issues if i["kind"] == "mismatch"] == ["inn"]


def test_check_docs_ignores_digits_not_next_to_labels(tmp_path, capsys):
    path = write(tmp_path, "n.md", f"Телефон 8001234567, заказ {INN10_BAD}, тинн 123.\n")
    code, issues = check(capsys, [path], answers=None)
    assert code == 0 and issues == []


def test_check_docs_mismatch_with_answers(tmp_path, capsys):
    text = f"ООО «Тест-Компания», ИНН {INN10_OK[1]}, ОГРН {OGRN13_OK[1]}.\n"
    code, issues = check(capsys, [write(tmp_path, "m.md", text)])
    mismatches = [i for i in issues if i["kind"] == "mismatch"]
    assert code == 1 and sorted(i["field"] for i in mismatches) == ["inn", "ogrn"]
    assert all(i["line"] == 1 for i in mismatches)
    assert not [i for i in issues if i["kind"].endswith("checksum")]


def test_check_docs_name_mismatch_and_unconfirmed_requisites(tmp_path, capsys):
    other_name = "Оператор ООО «Чужая Компания», ИНН 0098765437.\n"
    _, issues = check(capsys, [write(tmp_path, "n1.md", other_name)])
    assert [i["field"] for i in issues if i["kind"] == "mismatch"] == ["name"]
    name_ok_spacing = "Оператор ООО  «Тест-Компания»,\nИНН 0098765437.\n"
    assert check(capsys, [write(tmp_path, "n2.md", name_ok_spacing)])[1] == []

    answers = json.loads(ANSWERS.read_text(encoding="utf-8"))
    answers["owner"].update({"inn": None, "ogrn": None})
    path = tmp_path / "answers-null.json"
    path.write_text(json.dumps(answers), encoding="utf-8")
    _, issues = check(capsys, [write(tmp_path, "n3.md", "ООО «Тест-Компания», ИНН 0098765437, ОГРН 1020000000008.\n")],
                      answers=path)
    assert sorted(i["field"] for i in issues if i["kind"] == "mismatch") == ["inn", "ogrn"]


def test_check_docs_npd_owner_has_no_ogrn(tmp_path, capsys):
    answers = json.loads(ANSWERS.read_text(encoding="utf-8"))
    answers["owner"].update({"status": "npd", "name": "Иванов Иван", "inn": "009876543299", "ogrn": None})
    path = tmp_path / "answers-npd.json"
    path.write_text(json.dumps(answers), encoding="utf-8")
    doc = write(tmp_path, "npd.md", f"Иванов Иван, ИНН 009876543299, ОГРН {OGRN13_OK[0]}.\n")
    _, issues = check(capsys, [doc], answers=path)
    assert [i["field"] for i in issues if i["kind"] == "mismatch"] == ["ogrn"]


OFFER_BAD = (
    "# Публичная оферта\n\n"
    "5.1. Продавец  вправе\nОТМЕНИТЬ заказ в любое время.\n"
    "6.2. Цена может быть изменена после оформления заказа.\n"
    "7.1. Возможна «оплата только банковской картой».\n"
)


def test_check_docs_forbidden_clauses_in_offer(tmp_path, capsys):
    offer = write(tmp_path, "oferta.md", OFFER_BAD)
    code, issues = check(capsys, [offer], answers=None)
    assert code == 1
    forbidden = [i for i in issues if i["kind"] == "forbidden_clause"]
    assert [(i["line"], i["severity"], i["blocking"]) for i in forbidden] == [
        (3, "violation", True), (5, "violation", True), (6, "risk", False)]
    assert forbidden[0]["fragment"] == "Продавец вправе отменить заказ"
    assert forbidden[0]["violates"] == "ZoZPP st. 16 p. 2"


def test_check_docs_offer_detected_by_heading_and_not_applied_elsewhere(tmp_path, capsys):
    by_heading = write(tmp_path, "terms.md", "# Публичная оферта интернет-магазина\n\nПродавец вправе отменить заказ.\n")
    assert kinds(check(capsys, [by_heading], answers=None)[1]) == ["forbidden_clause"]
    policy = write(tmp_path, "policy.md", "# Политика\n\nПродавец вправе отменить заказ.\n")
    assert check(capsys, [policy], answers=None)[1] == []
    forced = check(capsys, [policy], "--kind", "offer", answers=None)[1]
    assert kinds(forced) == ["forbidden_clause"]
    clean_offer = write(tmp_path, "oferta2.md", "# Оферта\n\nПокупатель вправе вернуть товар.\n")
    assert check(capsys, [clean_offer], answers=None)[1] == []


def test_check_docs_forbidden_clauses_from_real_kb(tmp_path, capsys):
    offer = write(tmp_path, "oferta.md", "# Оферта\n\nСпоры рассматриваются по месту нахождения Продавца.\n")
    code, out = run_json("check_docs", [offer, "--kb", REAL_KB], capsys)
    assert code == 1 and out["issues"][0]["kind"] == "forbidden_clause" and out["issues"][0]["severity"] == "violation"


def test_check_docs_bad_input_exits_2(tmp_path, capsys):
    assert run_main("check_docs", [tmp_path / "missing.md", "--kb", KB], capsys)[0] == 2
    doc = write(tmp_path, "d.md", "x\n")
    assert run_main("check_docs", [doc, "--kb", KB, "--answers", tmp_path / "missing.json"], capsys)[0] == 2
    assert run_main("check_docs", [doc, "--kb", tmp_path / "nokb"], capsys)[0] == 2


def test_check_docs_cli_output_shape_for_check_run(tmp_path):
    doc = write(tmp_path, "d.md", "{{ИНН}}\n")
    page = write(tmp_path, "p.html", "{{СРОК_ХРАНЕНИЯ}}\n")
    result = run_cli("check_docs", doc, "--public", page, "--kb", KB, "--answers", ANSWERS)
    data = json.loads(result.stdout)
    assert result.returncode == 1 and isinstance(data["issues"], list)
    assert [(i["kind"], i["blocking"]) for i in data["issues"]] == [("placeholder_requisite", False),
                                                                    ("placeholder_fact", True)]
    assert data["files"] == [str(doc), str(page)] and data["public"] == [str(page)] and data["blocking"] == 1
    assert run_cli("check_docs", doc, "--kb", KB, "--answers", ANSWERS).returncode == 0


# --------------------------------------------------------------------------
# report.py verify
# --------------------------------------------------------------------------

def good_row(**overrides):
    row = {
        "req": "ru:t-always", "title": "Privacy policy page exists", "status": "present",
        "evidence": [{"file": "app/privacy/page.tsx", "line": 1}], "norm": "Test-FZ st. 1",
        "level": "mandatory", "confidence": "high", "effective_from": "2022-09-01", "source": "base",
        "sources": ["http://pravo.gov.ru/proxy/ips/?docbody=&nd=1"], "bucket": "done",
        "element": "tpl-policy:А1", "basis": "norm",
    }
    row.update(overrides)
    return row


def make_report(*rows, **extra):
    report = {"version": 1, "generated": TODAY, "product": {"name": "Test shop", "kinds": ["site"], "urls": []},
              "mode": "repo+prod", "rows": list(rows), "registries": [], "not_checked": []}
    report.update(extra)
    return report


def verify(tmp_path, report, capsys, *extra):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    code, out = run_main("report", ["verify", path, "--kb", KB, "--today", TODAY, *extra], capsys)
    return code, json.loads(out)


def test_verify_golden_passes(tmp_path, capsys):
    code, issues = verify(tmp_path, make_report(good_row()), capsys)
    assert code == 0 and issues == []


def test_verify_accepts_a_realistic_mixed_report(tmp_path, capsys):
    rows = [
        good_row(),
        good_row(req="ru:t-bylaw", element=None, level="conditional", status="missing", bucket="owner"),
        good_row(req=None, element=None, level="interpretation", basis="interpretation", status="partial",
                 bucket="disputed", confidence="low"),
        good_row(req="ru:t-future", element=None, level="conditional", status="not_visible", evidence=[],
                 effective_from="2027-03-01", bucket="roadmap"),
        good_row(req="ru:t-ios", element=None, level="recommended", source="platform", basis="platform",
                 sources=["https://developer.apple.com/app-store/review/"], bucket="owner", status="missing"),
        good_row(req="ru:t-analytics", element=None, level="conditional", source="official_runtime",
                 sources=["https://www.vsrf.ru/documents/1/", "http://publication.pravo.gov.ru/document/1"],
                 status="n_a", evidence=[], bucket="done"),
    ]
    code, issues = verify(tmp_path, make_report(*rows), capsys)
    assert issues == [] and code == 0


CASES = [
    ("unknown_req", {"req": "ru:no-such-id"}),
    ("unknown_element", {"element": "tpl-policy:Я99"}),
    ("unknown_element", {"element": "no-colon"}),
    # mandatory needs: basis norm, source base/official_runtime, law/bylaw, confidence != low, element норма+обязательно
    ("mandatory_unsupported", {"source": "market"}),
    ("mandatory_unsupported", {"source": "platform", "basis": "platform", "level": "mandatory"}),
    ("mandatory_unsupported", {"basis": "practice"}),
    ("mandatory_unsupported", {"basis": "interpretation"}),
    ("mandatory_unsupported", {"basis": "inference"}),
    ("mandatory_unsupported", {"req": "ru:t-practice", "element": None}),  # source_kind engineering
    ("mandatory_unsupported", {"req": "ru:t-ios", "element": None}),  # source_kind store-policy
    ("mandatory_unsupported", {"req": "ru:t-lowconf", "element": None}),  # legal_confidence low
    ("mandatory_unsupported", {"req": None, "element": None}),
    ("mandatory_unsupported", {"element": "tpl-policy:А2"}),  # element status рекомендуется
    ("mandatory_unsupported", {"element": "tpl-policy:А3"}),  # element status при условии
    ("mandatory_unsupported", {"element": "tpl-policy:А4"}),  # element method interpretation
    ("platform_level", {"level": "conditional", "source": "platform", "basis": "platform"}),
    ("platform_level", {"level": "conditional", "source": "base", "basis": "platform", "element": None}),
    ("source_not_allowlisted", {"source": "official_runtime", "sources": ["https://rg.ru/2026/doc.html"]}),
    ("source_not_allowlisted", {"source": "official_runtime", "sources": ["https://www.vsrf.ru/a", "https://consultant.ru/b"]}),
    ("source_not_allowlisted", {"source": "official_runtime", "sources": ["https://pravo.gov.ru.evil.example/a"]}),
    ("missing_evidence", {"evidence": []}),
    ("missing_evidence", {"status": "partial", "evidence": [], "level": "conditional", "element": None}),
    ("missing_evidence", {"status": "missing", "evidence": [], "level": "conditional", "element": None}),
    ("missing_evidence", {"evidence": [{"note": "somewhere"}]}),
    ("conditional_unsupported", {"level": "conditional", "basis": "practice"}),
    ("conditional_unsupported", {"level": "conditional", "source": "market"}),
    ("conditional_unsupported", {"level": "conditional", "req": "ru:t-practice", "element": None}),
    ("conditional_unsupported", {"level": "conditional", "req": "ru:t-lowconf", "element": None}),
    ("conditional_unsupported", {"level": "conditional", "req": None, "element": None}),
    ("conditional_unsupported", {"level": "conditional", "element": "tpl-policy:А4"}),  # element method interpretation
    ("conditional_unsupported", {"level": "conditional", "element": "tpl-policy:А2"}),  # element status рекомендуется
    ("level_basis_mismatch", {"level": "conditional", "basis": "interpretation"}),
    ("level_basis_mismatch", {"level": "mandatory", "basis": "practice"}),
    ("level_basis_mismatch", {"level": "conditional", "basis": "inference"}),
    ("level_basis_mismatch", {"level": "conditional", "source": "market"}),
    ("source_required", {"source": "official_runtime", "sources": []}),
    ("source_required", {"source": "official_runtime", "sources": None}),
    ("source_required", {"source": "platform", "basis": "platform", "level": "recommended", "sources": [],
                         "element": None}),
    ("source_not_allowlisted", {"source": "platform", "basis": "platform", "level": "recommended", "element": None,
                                "sources": ["https://example.com/developer.apple.com"]}),
    ("source_not_allowlisted", {"source": "official_runtime", "sources": ["https://evil.test\\@pravo.gov.ru/a"]}),
    ("source_not_allowlisted", {"source": "official_runtime", "sources": ["https://user@pravo.gov.ru/a"]}),
    ("element_req_mismatch", {"req": "ru:t-analytics"}),  # element А1 belongs to ru:t-always
    ("effective_from_unknown", {"effective_from": "2024-05-05"}),
    ("effective_from_unknown", {"req": "ru:t-mixed", "element": None, "level": "conditional",
                                "effective_from": "2026-01-01", "bucket": "owner"}),
    ("future_not_roadmap", {"req": "ru:t-future", "element": None, "level": "conditional",
                            "effective_from": "2027-03-01", "bucket": "owner"}),
    # the requirement itself starts in the future: roadmap even when the row names an earlier date of it
    ("future_not_roadmap", {"req": "ru:t-future-dates", "element": None, "level": "conditional",
                            "effective_from": "2025-01-01", "bucket": "owner"}),
    ("bad_type", {"req": 5}),
    ("bad_type", {"element": ["tpl-policy:А1"]}),
    ("bad_type", {"sources": "http://pravo.gov.ru/a"}),
    ("bad_type", {"sources": [5]}),
    ("bad_type", {"evidence": "app/page.tsx:1"}),
    ("bad_type", {"evidence": ["app/page.tsx:1"]}),
    ("bad_type", {"norm": 152}),
    ("bad_enum", {"level": ["mandatory"]}),
    ("future_not_roadmap", {"effective_from": "2027-03-01", "bucket": "owner"}),
    ("future_not_roadmap", {"effective_from": "2026-10-19", "bucket": "done"}),
    ("future_not_roadmap", {"req": "ru:t-future", "element": None, "effective_from": None, "bucket": "owner",
                            "level": "conditional"}),
    ("bad_enum", {"status": "maybe"}),
    ("bad_enum", {"level": "obligatory"}),
    ("bad_enum", {"bucket": "later"}),
    ("bad_enum", {"source": "wiki"}),
    ("bad_enum", {"basis": "guess"}),
    ("bad_enum", {"confidence": "certain"}),
    ("bad_enum", {"effective_from": "01.03.2027"}),
]


@pytest.mark.parametrize("rule,overrides", CASES, ids=[f"{r}-{i}" for i, (r, _) in enumerate(CASES)])
def test_verify_rule_fails(tmp_path, capsys, rule, overrides):
    code, issues = verify(tmp_path, make_report(good_row(**overrides)), capsys)
    assert code == 1
    assert rule in {i["rule"] for i in issues}, issues
    assert all(i["row"] == 0 for i in issues)


def test_verify_missing_required_field(tmp_path, capsys):
    row = good_row()
    del row["bucket"]
    code, issues = verify(tmp_path, make_report(row), capsys)
    assert code == 1 and "missing_field" in {i["rule"] for i in issues}


def test_verify_exemptions_that_must_not_fail(tmp_path, capsys):
    rows = [
        good_row(evidence=[{"url": "https://shop.example.test/privacy"}]),
        good_row(status="n_a", evidence=[], level="conditional", element=None),
        good_row(status="not_visible", evidence=[], level="conditional", element=None),
        good_row(req="ru:t-future", effective_from="2027-03-01", bucket="roadmap", level="conditional", element=None),
        good_row(req="ru:t-future-dates", effective_from="2025-01-01", bucket="roadmap", level="conditional",
                 element=None),
        good_row(level="conditional", req="ru:t-analytics", element="tpl-policy:А3"),  # element status при условии
        good_row(effective_from=None, level="recommended", source="market", basis="practice", sources=[],
                 element=None),
        good_row(req=None, element=None, effective_from="2030-01-01", bucket="roadmap", level="interpretation",
                 basis="interpretation"),  # no requirement: nothing to compare the date with
        good_row(source="platform", basis="platform", level="recommended", element=None,
                 sources=["https://developer.apple.com/app-store/review/", "https://www.rustore.ru/help"]),
        good_row(req="ru:t-mixed", element=None, level="conditional", effective_from="2025-09-01", bucket="owner"),
        good_row(req="ru:t-bylaw", element=None, level="mandatory"),
        good_row(source="official_runtime", sources=["https://pravo.gov.ru/a", "https://www.ksrf.ru/b"]),
        good_row(source="base", sources=["https://rg.ru/anything-goes-for-base"]),
        good_row(level="recommended", source="market", basis="practice", sources=[], element=None),
    ]
    code, issues = verify(tmp_path, make_report(*rows), capsys)
    assert issues == [], issues


def test_verify_future_by_requirement_dates_and_today(tmp_path, capsys):
    row = good_row(req="ru:t-future", element=None, effective_from=None, bucket="owner", level="conditional")
    assert verify(tmp_path, make_report(row), capsys)[0] == 1
    path = tmp_path / "late.json"
    path.write_text(json.dumps(make_report(row)), encoding="utf-8")
    code, out = run_main("report", ["verify", path, "--kb", KB, "--today", "2027-04-01"], capsys)
    assert code == 0 and json.loads(out) == []


def test_verify_sources_file(tmp_path, capsys):
    sources = tmp_path / "sources.json"
    sources.write_text(json.dumps([
        {"url": "https://pravo.gov.ru/a", "fetched_at": TODAY, "quote": "text", "kind": "official"},
        {"url": "https://developer.apple.com/x", "fetched_at": TODAY, "quote": "text", "kind": "platform"},
        {"url": "https://rg.ru/a", "fetched_at": TODAY, "quote": "text", "kind": "official"},
        {"url": "https://blog.example.test/a", "fetched_at": TODAY, "quote": "text", "kind": "market"},
        {"url": "https://example.com/developer.apple.com", "fetched_at": TODAY, "quote": "text", "kind": "platform"},
        {"url": "https://evil.test\\@pravo.gov.ru/", "fetched_at": TODAY, "quote": "text", "kind": "official"},
    ]), encoding="utf-8")
    code, issues = verify(tmp_path, make_report(good_row()), capsys, "--sources", sources)
    assert code == 1
    assert [(i["rule"], i["source"]) for i in issues] == [("source_not_allowlisted", 2), ("source_not_allowlisted", 4),
                                                         ("source_not_allowlisted", 5)]


TOURISM = "ru:sayt-turoperatora-i-turagenta"


def tourism_row(**overrides):
    row = good_row(req=TOURISM, element=None, level="conditional", status="missing", bucket="owner",
                   norm="132-FZ st. 9 ch. 8", effective_from="2022-01-01")
    row.update(overrides)
    return row


def write_answers(tmp_path, sectors):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"business": {"sectors": sectors}}), encoding="utf-8")
    return path


def verify_real_kb(tmp_path, report, capsys, *extra):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    code, out = run_main("report", ["verify", path, "--kb", REAL_KB, "--today", TODAY, *extra], capsys)
    return code, json.loads(out)


def test_verify_sectoral_row_needs_a_confirmed_sector_when_answers_are_given(tmp_path, capsys):
    report = make_report(tourism_row())
    assert verify_real_kb(tmp_path, report, capsys) == (0, [])  # without --answers the gate is off
    for sectors in ([], ["medical"], ["no-such-group"]):
        code, issues = verify_real_kb(tmp_path, report, capsys, "--answers", write_answers(tmp_path, sectors))
        assert code == 1, sectors
        assert [(i["rule"], i["row"], i["req"]) for i in issues] == [("sectoral_unconfirmed", 0, TOURISM)]
    code, issues = verify_real_kb(tmp_path, report, capsys, "--answers", write_answers(tmp_path, ["taxi-tourism"]))
    assert (code, issues) == (0, [])
    mandatory = make_report(tourism_row(level="mandatory"))
    code, issues = verify_real_kb(tmp_path, mandatory, capsys, "--answers", write_answers(tmp_path, []))
    assert "sectoral_unconfirmed" in {i["rule"] for i in issues}


def test_verify_sectoral_gate_ignores_other_requirements_soft_levels_and_not_applicable_rows(tmp_path, capsys):
    rows = [
        good_row(),  # a general requirement
        good_row(req="ru:t-analytics", element=None, level="conditional"),  # conditional by features, not sectoral
        tourism_row(level="interpretation", basis="interpretation", confidence="low"),
        tourism_row(level="recommended", source="market", basis="practice", sources=[]),
        tourism_row(status="n_a", evidence=[], bucket="done"),  # a sector rule ruled out is reported as n_a
        good_row(req=None, element=None, level="interpretation", basis="interpretation"),
    ]
    code, issues = verify_real_kb(tmp_path, make_report(*rows), capsys, "--answers", write_answers(tmp_path, []))
    assert [i["rule"] for i in issues if i["rule"] == "sectoral_unconfirmed"] == []


def test_verify_sectoral_gate_on_the_fixture_pack_and_answers_without_a_business_section(tmp_path, capsys):
    row = good_row(req="ru:t-medical", element=None, level="conditional")
    report = make_report(row)
    assert verify(tmp_path, report, capsys, "--answers", write_answers(tmp_path, ["medical"])) == (0, [])
    code, issues = verify(tmp_path, report, capsys, "--answers", write_answers(tmp_path, []))
    assert code == 1 and [i["rule"] for i in issues] == ["sectoral_unconfirmed"]
    bare = tmp_path / "bare.json"
    bare.write_text("{}", encoding="utf-8")
    code, issues = verify(tmp_path, report, capsys, "--answers", bare)
    assert code == 1 and [i["rule"] for i in issues] == ["sectoral_unconfirmed"]


def test_verify_sectoral_requirement_outside_the_map_group_is_not_confirmed_by_another_group(tmp_path, capsys):
    # ru:t-sector-b is sectoral but no group of the fixture map lists it, so no confirmed group covers it
    report = make_report(good_row(req="ru:t-sector-b", element=None, level="conditional"))
    code, issues = verify(tmp_path, report, capsys, "--answers", write_answers(tmp_path, ["medical"]))
    assert code == 1 and [i["rule"] for i in issues] == ["sectoral_unconfirmed"]


def test_verify_answers_bad_input_exits_2(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(json.dumps(make_report(good_row())), encoding="utf-8")
    base = ("report", "verify", report, "--kb", KB, "--today", TODAY, "--answers")
    assert run_cli(*base, write_answers(tmp_path, [])).returncode == 0
    assert run_cli(*base, tmp_path / "missing.json").returncode == 2
    junk = tmp_path / "junk.json"
    junk.write_text("not json", encoding="utf-8")
    assert run_cli(*base, junk).returncode == 2
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"business": {"sectors": "medical"}}), encoding="utf-8")
    assert run_cli(*base, wrong).returncode == 2


def test_verify_cli_exit_codes_and_stdout_is_a_json_list(tmp_path):
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps(make_report(good_row())), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(make_report(good_row(req="ru:nope"))), encoding="utf-8")
    passed = run_cli("report", "verify", ok, "--kb", KB, "--today", TODAY)
    failed = run_cli("report", "verify", bad, "--kb", KB, "--today", TODAY)
    assert passed.returncode == 0 and json.loads(passed.stdout) == []
    assert failed.returncode == 1 and json.loads(failed.stdout)[0]["rule"] == "unknown_req"
    assert run_cli("report", "verify", tmp_path / "missing.json", "--kb", KB).returncode == 2
    junk = tmp_path / "junk.json"
    junk.write_text("not json", encoding="utf-8")
    assert run_cli("report", "verify", junk, "--kb", KB).returncode == 2
    assert run_cli("report", "verify", ok, "--kb", KB, "--today", "yesterday").returncode == 2


def test_verify_refuses_a_bare_list_of_rows(tmp_path):
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([good_row()]), encoding="utf-8")
    assert run_cli("report", "verify", path, "--kb", KB, "--today", TODAY).returncode == 2


def top_issues(tmp_path, capsys, mutate):
    report = make_report(good_row())
    mutate(report)
    code, issues = verify(tmp_path, report, capsys)
    return code, [(i["rule"], i.get("key")) for i in issues if i["row"] is None]


def test_verify_top_level_keys_and_enums(tmp_path, capsys):
    for key in ("version", "generated", "product", "mode", "registries", "not_checked"):
        code, found = top_issues(tmp_path, capsys, lambda r, key=key: r.pop(key))
        assert code == 1 and ("missing_field", key) in found, key
    assert top_issues(tmp_path, capsys, lambda r: r.update(version=2))[1] == [("bad_enum", "version")]
    for version in (True, 1.0, "1", None):  # True == 1 in Python: the type is checked as well
        assert top_issues(tmp_path, capsys, lambda r, v=version: r.update(version=v))[1] == [("bad_enum", "version")]
    assert top_issues(tmp_path, capsys, lambda r: r.update(mode="live"))[1] == [("bad_enum", "mode")]
    assert top_issues(tmp_path, capsys, lambda r: r.update(lang="de"))[1] == [("bad_enum", "lang")]
    assert top_issues(tmp_path, capsys, lambda r: r.update(product="shop"))[1] == [("bad_type", "product")]
    assert top_issues(tmp_path, capsys, lambda r: r.update(registries=[{"name": "x", "status": "maybe"}]))[1] == [
        ("bad_enum", "registries")]
    assert top_issues(tmp_path, capsys, lambda r: r.update(not_checked="nothing"))[1] == [("bad_type", "not_checked")]
    assert top_issues(tmp_path, capsys, lambda r: r.update(owner_checklist=[1]))[1] == [("bad_type", "owner_checklist")]


def test_verify_top_level_accepts_the_optional_keys_and_all_modes(tmp_path, capsys):
    for mode in ("repo+prod", "prod-only", "repo-only"):
        code, found = top_issues(tmp_path, capsys, lambda r, mode=mode: r.update(
            mode=mode, lang="en", owner_checklist=["Contract with the counter vendor"],
            registries=[{"name": "egrul", "status": "ok"}, {"name": "rkn", "status": "manual"},
                        {"name": "x", "status": "not_found"}, {"name": "y", "status": "error"}]))
        assert code == 0 and found == [], mode


def test_verify_accepts_an_evidence_note_and_rejects_a_non_string_one(tmp_path, capsys):
    removed = [{"file": "app/offer/page.tsx", "line": 17, "note": "до правок"}, {"file": "app/offer/page.tsx", "line": 3}]
    code, issues = verify(tmp_path, make_report(good_row(evidence=removed)), capsys)
    assert code == 0 and issues == []
    code, issues = verify(tmp_path, make_report(good_row(evidence=[{"url": "https://x.test/", "note": 5}])), capsys)
    assert code == 1 and [i["rule"] for i in issues] == ["bad_type"]


def test_verify_bad_types_never_crash(tmp_path, capsys):
    rows = [good_row(req={"a": 1}), good_row(evidence=None, status="n_a"), good_row(sources=None),
            good_row(status=["present"]), good_row(bucket=None), good_row(effective_from=20270301)]
    code, issues = verify(tmp_path, make_report(*rows), capsys)
    assert code == 1 and {i["rule"] for i in issues} >= {"bad_type", "bad_enum"}
    junk = make_report("not an object", 5, None)
    code, issues = verify(tmp_path, junk, capsys)
    assert code == 1 and [i["rule"] for i in issues] == ["bad_type"] * 3


# --------------------------------------------------------------------------
# report.py render
# --------------------------------------------------------------------------

def render_report():
    return make_report(
        good_row(title="Privacy policy | page exists"),
        good_row(req="ru:t-analytics", element=None, level="conditional", status="missing", bucket="owner",
                 title="Counters load before consent", evidence=[{"file": "app/page.tsx", "line": 12}, {"url": "https://shop.example.test/"}]),
        good_row(req=None, element=None, level="interpretation", basis="interpretation", status="partial",
                 bucket="disputed", confidence="low", title="Trial turns into a paid plan"),
        good_row(req="ru:t-future", element=None, level="conditional", status="not_visible", evidence=[],
                 effective_from="2027-03-01", bucket="roadmap", title="Notice about rights to results"),
        registries=[{"name": "egrul", "status": "ok", "url": "https://egrul.nalog.ru/", "note": "entry found"},
                    {"name": "rkn-operators", "status": "manual", "url": "https://pd.rkn.gov.ru/operators-registry/operators-list/",
                     "note": "open from a Russian IP"}],
        not_checked=["Cookies before consent: JS was not executed"],
    )


def render(tmp_path, report, capsys, *extra):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    code, out = run_main("report", ["render", path, "--kb", KB, *extra], capsys)
    assert code == 0
    return out


def test_render_ru_sections_and_base_line(tmp_path, capsys):
    md = render(tmp_path, render_report(), capsys, "--lang", "ru")
    for heading in ("## Сделано", "## Сделать вам", "## Спорно", "## Дорожная карта", "## Реестры", "## Что не проверялось"):
        assert heading in md, heading
    lines = md.splitlines()
    assert lines[0].startswith("# ")
    assert "Test shop" in md and "repo+prod" in md and TODAY in md
    assert lines.count("База требований: 2026-10-16") == 1
    assert not any(word in md.lower() for word in ("устарел", "outdated", "stale"))
    assert [l for l in lines if l.strip()][-1] == "Не юридическая консультация."
    # grouped by direction: A (Privacy policy), C (counters), N (future)
    assert md.index("Counters load before consent") > md.index("## Сделать вам")
    assert md.index("Notice about rights to results") > md.index("## Дорожная карта")
    assert "2027-03-01" in md.split("## Дорожная карта")[1].split("## Реестры")[0]
    assert "Privacy policy \\| page exists" in md  # table cell escaping
    assert "app/page.tsx:12" in md and "https://shop.example.test/" in md
    assert "https://egrul.nalog.ru/" in md and "open from a Russian IP" in md
    assert "Cookies before consent: JS was not executed" in md
    assert "Субъекты и юрисдикция" in md  # direction A heading


def test_render_prints_the_evidence_note(tmp_path, capsys):
    report = make_report(good_row(evidence=[{"file": "app/offer/page.tsx", "line": 17, "note": "до правок"},
                                            {"url": "https://shop.example.test/", "note": "снимок"}]))
    md = render(tmp_path, report, capsys, "--lang", "ru")
    assert "app/offer/page.tsx:17 (до правок)" in md and "https://shop.example.test/ (снимок)" in md


def test_render_owner_checklist_section(tmp_path, capsys):
    report = render_report()
    report["owner_checklist"] = ["Contract with the counter vendor", "Order on the person responsible for data"]
    ru = render(tmp_path, report, capsys, "--lang", "ru")
    assert ru.index("## Реестры") < ru.index("## Запрос документов") < ru.index("## Что не проверялось")
    assert "- Contract with the counter vendor" in ru
    en = render(tmp_path, report, capsys, "--lang", "en")
    assert en.index("## Registries") < en.index("## Documents to provide") < en.index("## Not checked")
    assert "## Запрос документов" not in render(tmp_path, render_report(), capsys, "--lang", "ru")  # optional


def test_render_en(tmp_path, capsys):
    md = render(tmp_path, render_report(), capsys, "--lang", "en")
    for heading in ("## Done", "## To do (owner)", "## Disputed", "## Roadmap", "## Registries", "## Not checked"):
        assert heading in md, heading
    assert md.splitlines().count("Requirements base: 2026-10-16") == 1
    assert [l for l in md.splitlines() if l.strip()][-1] == "Not legal advice."
    assert "Subjects and jurisdiction" in md


def test_render_language_from_report_when_flag_is_absent(tmp_path, capsys):
    report = render_report()
    report["lang"] = "en"
    assert "Not legal advice." in render(tmp_path, report, capsys)
    assert "Не юридическая консультация." in render(tmp_path, report, capsys, "--lang", "ru")
    del report["lang"]
    assert "Не юридическая консультация." in render(tmp_path, report, capsys)


def test_render_empty_sections_and_rows_without_requirement(tmp_path, capsys):
    report = make_report(good_row(req=None, element=None, level="recommended", basis="practice", bucket="owner",
                                  title="Add a footer link"))
    md = render(tmp_path, report, capsys, "--lang", "ru")
    assert "## Сделано" in md and "Add a footer link" in md
    assert "Нет." in md
    assert "Прочее" in md  # rows without a requirement land in the catch-all group


def test_render_survives_wrongly_typed_reports(tmp_path, capsys):
    report = {"version": True, "generated": 20261018, "product": {"name": ["x"], "kinds": "site", "urls": [1, None]},
              "mode": {"a": 1}, "registries": ["x", {"name": 5, "status": ["ok"], "url": None, "note": {"k": 1}}],
              "not_checked": "just text", "owner_checklist": [1, None, "ok"], "lang": "en",
              "rows": [{"req": ["ru:t-always"], "title": 5, "status": ["present"], "level": 3, "bucket": "done",
                        "evidence": "app/page.tsx:1", "norm": 152, "confidence": {}, "source": None},
                       {"req": 7, "title": None, "bucket": ["owner"]}, "junk", 3,
                       {"req": "ru:t-always", "title": "ok", "bucket": "roadmap", "effective_from": 20270301,
                        "evidence": [5, {"file": "a.py", "line": 3}, {"url": "https://x.test"}]}]}
    md = render(tmp_path, report, capsys, "--lang", "en")
    assert "## Done" in md and "app/page.tsx" not in md and "a.py:3" in md and md.rstrip().endswith("Not legal advice.")
    for lang_value in ("en", "ru"):
        report["lang"] = lang_value
        render(tmp_path, report, capsys)


def test_render_bad_input_exits_2(tmp_path, capsys):
    assert run_cli("report", "render", tmp_path / "missing.json", "--kb", KB).returncode == 2
    path = tmp_path / "r.json"
    path.write_text(json.dumps(make_report(good_row())), encoding="utf-8")
    assert run_cli("report", "render", path, "--kb", KB, "--lang", "de").returncode == 2


# --------------------------------------------------------------------------
# Catalog host rule, needle gate, file classes, speed
# --------------------------------------------------------------------------

def test_host_rule_subdomain_lookalike_and_path_prefix():
    index = load("_kb").HostIndex()
    index.add("web", "mc.yandex.ru")
    index.add("tg", "telegram.org/js/telegram-widget")
    index.add("hosting", "vercel.app")
    assert index.lookup("mc.yandex.ru") == ["web"]
    assert index.lookup("informer.mc.yandex.ru", "/x.js") == ["web"]  # subdomain
    assert index.lookup("MC.Yandex.RU.", "/") == ["web"]  # case and trailing dot
    for lookalike in ("mc.yandex.ru.evil.test", "evilmc.yandex.ru", "notmc.yandex.ru", "yandex.ru"):
        assert index.lookup(lookalike, "/metrika/tag.js") == [], lookalike
    assert index.lookup("telegram.org", "/js/telegram-widget.js") == ["tg"]  # path prefix
    assert index.lookup("www.telegram.org", "/js/telegram-widget.js?22") == ["tg"]
    assert index.lookup("telegram.org", "/other.js") == []
    assert index.lookup("telegram.org", "") == []
    assert index.lookup("shop.vercel.app", "/") == ["hosting"]  # suffix-style entry
    assert index.lookup("vercel.app.example.com") == []


def test_host_rule_finds_urls_and_bare_hosts_in_text_not_substrings():
    index = load("_kb").HostIndex()
    index.add("web", "mc.yandex.ru")
    index.add("tg", "telegram.org/js/telegram-widget")
    text = (
        '<script src="https://mc.yandex.ru/metrika/tag.js"></script>\n'
        "<script src='//telegram.org/js/telegram-widget.js?22'></script>\n"
        'x = "https://telegram.org/other.js"; y = "mc.yandex.ru.evil.test/a"; z = "evilmc.yandex.ru";\n'
        "mail = user@mc.yandex.ru; this.props.name = 1; host: informer.mc.yandex.ru\n"
    )
    found = [(matched, owner) for _, matched, owner in index.find_in(text)]
    assert found == [("mc.yandex.ru/metrika/tag.js", "web"), ("telegram.org/js/telegram-widget.js?22", "tg"),
                     ("informer.mc.yandex.ru", "web")]


def test_scan_repo_applies_host_rule(repo, capsys):
    features = feature_by_id(scan_repo(repo, capsys))
    counter = [e for e in features["analytics.web_counter"]["evidence"] if e["file"] == "public/widgets.html"]
    assert [e["match"] for e in counter] == ["informer.mc.yandex.ru/x.js"]  # subdomain yes, look-alike no
    telegram = [e["match"] for e in features["auth.telegram_login"]["evidence"] if e["file"] == "public/widgets.html"]
    assert "telegram.org/js/telegram-widget.js?22" in telegram
    assert not any("other.js" in match for match in telegram)  # path prefix not met


def test_scan_url_applies_host_rule(scanned):
    base, out, _ = scanned
    features = {f["id"]: f["evidence"] for f in out["features"]}
    counter = [e["match"] for e in features["analytics.web_counter"] if e["kind"] == "host"]
    assert "mc.yandex.ru/metrika/tag.js" in counter and not any("evil.test" in m for m in counter)
    telegram = [e["match"] for e in features["auth.telegram_login"]]
    assert "telegram.org/js/telegram-widget.js?22" in telegram and not any("other.js" in m for m in telegram)
    assert all(e["page"].startswith(base) for items in features.values() for e in items)


def test_scan_repo_file_classes(repo, capsys):
    features = feature_by_id(scan_repo(repo, capsys))
    files = {e["file"] for e in features["analytics.web_counter"]["evidence"]}
    assert not files & {"docs/guide.md", "secrets/keys.json", "server.pem", ".env", "vendor_lib.js"}
    # a Cyrillic keyword pattern runs on markup/UI/text files only, not on Python source
    school = {e["file"] for e in features["sector.education_test"]["evidence"]}
    assert school == {"public/school.html"}


def test_scan_repo_gate_gives_the_same_evidence_as_running_every_regex():
    module = load("scan_repo")
    total = 0
    for root in (FIX / "repo", FIX / "repo_flutter", REAL_KB / "templates"):
        for catalog in (CATALOG, REAL_CATALOG):
            if not catalog.is_file():
                continue
            gated = module.scan(str(root), str(catalog), gate=True)
            ungated = module.scan(str(root), str(catalog), gate=False)
            assert gated["features"] == ungated["features"], (root, catalog)
            total += sum(len(f["evidence"]) for f in gated["features"])
    assert total > 100  # the corpus really triggers many patterns


def random_pattern(rng, depth=0):
    """(regex, a string it matches) from a small grammar."""
    kinds = ["lit", "lit", "lit", "class", "word", "qchar"]
    if depth < 2:
        kinds += ["alt", "opt", "plus", "seq", "seq", "look", "group"]
    kind = rng.choice(kinds)
    if kind == "lit":
        word = "".join(rng.choice("abcdefghklmnoprstu") for _ in range(rng.randint(1, 7)))
        return word, word
    if kind == "class":
        return "[abc]", rng.choice("abc")
    if kind == "word":
        return r"\w+", "xy"
    if kind == "qchar":
        char = rng.choice("abc")
        quantifier, counts = rng.choice([("?", (0, 1)), ("*", (0, 1, 2)), ("+", (1, 2)), ("{2}", (2,)),
                                         ("{1,3}", (1, 2, 3)), ("{0,2}", (0, 1, 2))])
        return char + quantifier, char * rng.choice(counts)
    if kind == "alt":
        parts = [random_pattern(rng, depth + 1) for _ in range(rng.randint(2, 3))]
        return "(?:" + "|".join(p for p, _ in parts) + ")", rng.choice(parts)[1]
    if kind == "opt":
        pattern, sample = random_pattern(rng, depth + 1)
        return "(?:" + pattern + ")?", rng.choice([sample, ""])
    if kind == "plus":
        pattern, sample = random_pattern(rng, depth + 1)
        return "(?:" + pattern + ")+", sample * rng.randint(1, 2)
    if kind == "seq":
        parts = [random_pattern(rng, depth + 1) for _ in range(rng.randint(2, 4))]
        return "".join(p for p, _ in parts), "".join(s for _, s in parts)
    if kind == "look":
        pattern, sample = random_pattern(rng, depth + 1)
        return "(?!zzzz)" + pattern, sample
    pattern, sample = random_pattern(rng, depth + 1)
    return "(" + pattern + ")", sample


def test_literal_needles_are_sound_on_random_patterns():
    kb = load("_kb")
    import re as regex
    rng = random.Random(20261018)
    checked = gated = 0
    for _ in range(2500):
        pattern, sample = random_pattern(rng)
        flags = ""
        if rng.random() < 0.4:
            flags = "(?i)"
            sample = "".join(c.upper() if rng.random() < 0.5 else c for c in sample)
        text = "qq " + sample + " qq"
        if not regex.search(flags + pattern, text):
            continue
        checked += 1
        needles = kb.literal_needles(flags + pattern)
        if needles is not None:
            gated += 1
            assert any(n in text.lower() for n in needles), (flags + pattern, text, needles)
    assert checked > 1800 and gated > 400


def test_literal_needles_on_known_patterns():
    kb = load("_kb")
    assert kb.literal_needles(r"\bym\(") == frozenset({"ym("})
    assert kb.literal_needles(r"\bym\b") is None  # 'ym' is shorter than 3 characters: run the regex always
    assert kb.literal_needles(r"(?i)\b(?:openvpn|wireguard|v2ray)\b") == frozenset({"openvpn", "wireguard", "v2ray"})
    assert kb.literal_needles(r"colou?r\s+scheme") == frozenset({"scheme"})  # longest required literal wins
    assert kb.literal_needles(r"(?i)mailchimp|unisender") == frozenset({"mailchimp", "unisender"})
    assert kb.literal_needles(r"(?<![\w.])telegram\.org/js") == frozenset({"telegram.org/js"})
    assert kb.literal_needles(r"[a-z]+\d*") is None
    assert kb.literal_needles(r"(abc)\1") is None  # back-reference: not modelled
    assert kb.literal_needles(r"(?(1)yes|no)") is None
    assert kb.literal_needles("(?x) foo bar # comment") is None  # verbose mode ignores spaces: not modelled
    assert kb.literal_needles(r"foo(?:bar)?") == frozenset({"foo"})
    assert kb.literal_needles("x" * 80) == frozenset({"x" * 40})  # long literals are cut to a prefix


@pytest.mark.skipif(not REAL_CATALOG.is_file(), reason="catalog not written yet")
def test_real_catalog_compiles_and_every_host_entry_is_host_or_host_path():
    kb = load("_kb")
    catalog = kb.load_catalog(REAL_CATALOG)
    assert catalog.warnings == []
    assert len(catalog.features) >= 60
    entries = [h for e in json.loads(REAL_CATALOG.read_text(encoding="utf-8")) for h in e.get("hosts", [])]
    assert entries and not [h for h in entries if "://" in h or h.startswith(("/", "*")) or " " in h]


def test_catalog_gate_matches_ungated_on_random_catalogs():
    kb = load("_kb")
    for seed in range(8):
        rng = random.Random(seed)
        entries, samples = [], []
        for number in range(40):
            pattern, sample = random_pattern(rng)
            entries.append({"id": "f%d" % number, "code": ["(?i)" + pattern], "dom": [pattern]})
            samples.append(sample)
        catalog = kb.Catalog(entries)
        text = " ".join(rng.sample(samples, 12)) + " lorem ipsum " + " ".join(rng.sample(samples, 5))
        text = "".join(c.upper() if rng.random() < 0.2 else c for c in text)
        gated = list(catalog.pattern_matches(text, per_pattern=50, gate=True))
        assert gated == list(catalog.pattern_matches(text, per_pattern=50, gate=False)), seed
        assert gated


def make_big_repo(root, count, seed=5):
    """A tree of many files with realistic words, to exercise the needle gate; returns its size in bytes."""
    rng = random.Random(seed)
    words = ("login password email payment cart order token session user profile обработка согласие оплата "
             "заказ корзина подписка регистрация form submit fetch request response store cookie consent "
             "analytics counter customer address phone delivery refund price discount").split()
    size = 0
    for number in range(count):
        ext = (".tsx", ".html", ".py", ".js", ".md")[number % 5]
        lines = []
        for _ in range(110):
            lines.append("  const %s_%d = call('%s', {%s: '%s'}) // %s" % (
                rng.choice(words), rng.randint(0, 99), rng.choice(words), rng.choice(words), rng.choice(words),
                " ".join(rng.choice(words) for _ in range(5))))
        if number == 7:
            lines.append("ym(12345678, 'init');")
        if number == 8:
            lines.append("<script src='https://api.openai.com/v1/x'></script>")
        text = "\n".join(lines) + "\n"
        target = root / ("src%d" % (number % 12)) / ("f%d%s" % (number, ext))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        size += len(text.encode("utf-8"))
    return size


@pytest.mark.skipif(not REAL_CATALOG.is_file(), reason="catalog not written yet")
def test_scan_repo_gated_output_equals_ungated_on_a_generated_tree(tmp_path):
    module = load("scan_repo")
    root = tmp_path / "gen"
    assert make_big_repo(root, 60) > 500 * 1024
    gated = module.scan(str(root), str(REAL_CATALOG), gate=True)
    ungated = module.scan(str(root), str(REAL_CATALOG), gate=False)
    assert gated == ungated
    found = {f["id"] for f in gated["features"]}
    assert {"analytics.web_counter", "tech.generative_ai"} <= found  # the planted markers were found


@pytest.mark.skipif(not REAL_CATALOG.is_file() or os.environ.get("LEGAL_KIT_PERF") != "1",
                    reason="timing check: set LEGAL_KIT_PERF=1")
def test_scan_repo_six_megabyte_repo_runs_well_under_ten_seconds(tmp_path):
    root = tmp_path / "big"
    assert make_big_repo(root, 600) > 5.5 * 1024 * 1024
    started = time.perf_counter()
    result = run_cli("scan_repo", root, "--catalog", REAL_CATALOG)
    elapsed = time.perf_counter() - started
    assert result.returncode == 0, result.stderr
    assert elapsed < 10, "scan took %.1f s" % elapsed
    assert "analytics.web_counter" in {f["id"] for f in json.loads(result.stdout)["features"]}


# --------------------------------------------------------------------------
# 0.2: bot product kind and direction O
# --------------------------------------------------------------------------

def test_products_include_bot():
    assert load("_kb").PRODUCTS == ("site", "webapp", "ios", "android", "bot")


def test_report_has_direction_o():
    assert load("report").DIRECTIONS["O"] == ("Боты и мини-приложения в мессенджерах", "Bots and mini apps in messengers")


def test_detect_stacks_adds_bot_for_aiogram():
    stacks, _ = load("scan_repo").detect_stacks(["bot.py", "requirements.txt"], {}, "aiogram==3.13.1\n", "", "")
    assert {"python", "bot"} <= set(stacks)


def test_detect_stacks_adds_bot_for_grammy_and_max():
    scan = load("scan_repo")
    assert "bot" in scan.detect_stacks(["src/bot.ts", "package.json"], {"grammy": "^1"}, "", "", "")[0]
    assert "bot" in scan.detect_stacks(["src/bot.ts", "package.json"], {"@maxhub/max-bot-api": "^0.2"}, "", "", "")[0]


def test_detect_stacks_no_bot_for_plain_site():
    stacks, _ = load("scan_repo").detect_stacks(["app/page.tsx", "package.json"], {"next": "15"}, "", "", "")
    assert "bot" not in stacks


# --------------------------------------------------------------------------
# 0.2: select.py --planned
# --------------------------------------------------------------------------

def test_select_planned_feature_has_its_own_reason(capsys):
    code, out = run_json("select", select_args("--planned", "analytics.web_counter", "--subject", "ul",
                                               "--models", "b2c", "--products", "site"), capsys)
    assert code == 0
    why = {i["id"]: i["why"] for i in out["applicable"]}
    assert why["ru:t-analytics"] == ["planned:analytics.web_counter"]
    assert out["feature_sources"] == {"analytics.web_counter": ["planned"]}
    assert out["template_reasons"]["tpl-banner"] == ["planned:analytics.web_counter"]
    assert out["inputs"]["planned"] == ["analytics.web_counter"]
    assert list(out)[:2] == ["inputs", "feature_sources"]


def test_select_planned_and_found_is_one_row_with_both_reasons(capsys):
    code, out = run_json("select", select_args("--features", "analytics.web_counter",
                                               "--planned", "analytics.web_counter"), capsys)
    assert code == 0
    rows = [i for i in out["applicable"] if i["id"] == "ru:t-analytics"]
    assert len(rows) == 1 and rows[0]["why"] == ["feature:analytics.web_counter", "planned:analytics.web_counter"]
    assert out["feature_sources"]["analytics.web_counter"] == ["found", "planned"]


def test_select_unknown_planned_feature_only_warns(capsys):
    code, out = run_json("select", select_args("--planned", "lottery.weekly"), capsys)
    assert code == 0
    assert any("lottery.weekly" in w for w in out["warnings"])
    assert not any(r.startswith("planned:lottery") for i in out["applicable"] for r in i["why"])


def test_select_does_not_read_planned_from_answers(tmp_path, capsys):
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"version": 1, "product": {
        "kinds": ["site"], "planned_features": [{"id": "analytics.web_counter", "quote": "Метрика"}]}}),
        encoding="utf-8")
    code, out = run_json("select", select_args("--answers", answers), capsys)
    assert code == 0
    assert "ru:t-analytics" not in {i["id"] for i in out["applicable"]}
    assert out["inputs"]["planned"] == [] and out["feature_sources"] == {}
