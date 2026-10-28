"""Checks for the best-practice rules library (skills/legal-kit/references/rules) and scripts/rules.py.

Stdlib only. Every rule names requirement ids of the knowledge pack, so a rule can never claim a
norm the pack does not hold; the label a rule carries is checked against the requirement records.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "legal-kit"
RULES_DIR = SKILL / "references" / "rules"
STACKS_DIR = SKILL / "references" / "stacks"
KB_DIR = SKILL / "references" / "jurisdictions" / "ru"
CATALOG = SKILL / "references" / "features" / "catalog.json"
SCRIPTS = SKILL / "scripts"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_stacks import CITATION_RE, DATE_AMOUNT_RE  # noqa: E402

KEYS = {"id", "title_ru", "title_en", "reqs", "basis", "features", "always", "products", "stacks"}
BASES = {"norm", "practice", "interpretation", "platform"}
SECTIONS = ("## Why", "## Incorrect", "## Correct", "## In your stack")
PRIVATE = ("raw/articles", "raw/notes", "[[", "../topics/", "/Us" + "ers/", "llm" + "-wiki", "wiki/concepts",
           "wiki/references")


def load_kb():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("_kb", SCRIPTS / "_kb.py")
    if "_kb" in sys.modules:
        return sys.modules["_kb"]
    module = importlib.util.module_from_spec(spec)
    sys.modules["_kb"] = module
    spec.loader.exec_module(module)
    return module


def rule_files():
    return sorted(p for p in RULES_DIR.glob("*.md") if p.name != "README.md")


def rules():
    return load_kb().load_rules(str(RULES_DIR))


def requirements():
    return {json.loads(line)["id"]: json.loads(line) for line in (KB_DIR / "requirements.jsonl").open(encoding="utf-8")}


def catalog_ids():
    return {f["id"] for f in json.loads(CATALOG.read_text(encoding="utf-8"))}


def body(path):
    return path.read_text(encoding="utf-8").split("\n---\n", 1)[1]


def test_library_has_between_25_and_40_rules():
    assert 25 <= len(rule_files()) <= 40, len(rule_files())


def test_rules_index_lists_every_rule_file():
    index = (RULES_DIR / "README.md").read_text(encoding="utf-8")
    linked = set(re.findall(r"\]\(([a-z0-9-]+)\.md\)", index))
    assert linked == {p.stem for p in rule_files()}


def test_rule_frontmatter_shape():
    loaded = rules()
    assert set(loaded) == {p.stem for p in rule_files()}
    for rule_id, rule in loaded.items():
        assert set(rule) - {"path"} == KEYS, rule_id
        assert rule["id"] == rule_id
        assert rule["title_ru"] and rule["title_en"], rule_id
        assert rule["reqs"] and all(r.startswith("ru:") for r in rule["reqs"]), rule_id
        assert rule["basis"] in BASES, rule_id
        assert isinstance(rule["always"], bool), rule_id
        assert rule["always"] or rule["features"], f"{rule_id}: needs features or always: true"


def test_rule_reqs_exist():
    known = requirements()
    for rule_id, rule in rules().items():
        missing = [r for r in rule["reqs"] if r not in known]
        assert not missing, f"{rule_id}: unknown requirements {missing}"


def test_rule_norm_basis_needs_law_with_confidence():
    known = requirements()
    for rule_id, rule in rules().items():
        if rule["basis"] == "norm":
            for req in rule["reqs"]:
                record = known[req]
                assert record["source_kind"] in ("law", "bylaw"), f"{rule_id}: {req} is {record['source_kind']}"
                assert record["legal_confidence"] != "low", f"{rule_id}: {req} has low confidence"


def test_rule_platform_basis_only_for_store_policy():
    known = requirements()
    for rule_id, rule in rules().items():
        kinds = {known[r]["source_kind"] for r in rule["reqs"]}
        if "store-policy" in kinds:
            assert rule["basis"] == "platform", rule_id
        if rule["basis"] == "platform":
            assert kinds == {"store-policy"}, rule_id
        if kinds == {"engineering"}:
            assert rule["basis"] == "practice", rule_id


def test_rule_features_products_and_stacks_exist():
    features = catalog_ids()
    stacks = {p.stem for p in STACKS_DIR.glob("*.md")}
    products = set(load_kb().PRODUCTS)
    for rule_id, rule in rules().items():
        assert set(rule["features"]) <= features, f"{rule_id}: {sorted(set(rule['features']) - features)}"
        assert set(rule["stacks"]) <= stacks, f"{rule_id}: {sorted(set(rule['stacks']) - stacks)}"
        assert set(rule["products"]) <= products, rule_id


@pytest.mark.parametrize("path", rule_files(), ids=lambda p: p.stem)
def test_rule_bodies_have_no_citations_dates_amounts(path):
    text = body(path)
    assert not CITATION_RE.search(text), f"{path.name}: {CITATION_RE.search(text).group(0)!r}"
    assert not DATE_AMOUNT_RE.search(text), f"{path.name}: {DATE_AMOUNT_RE.search(text).group(0)!r}"


@pytest.mark.parametrize("path", sorted(RULES_DIR.glob("*.md")), ids=lambda p: p.stem)
def test_rules_have_no_private_patterns(path):
    text = path.read_text(encoding="utf-8")
    for bad in PRIVATE:
        assert bad not in text, f"{path.name} leaks {bad!r}"


@pytest.mark.parametrize("path", rule_files(), ids=lambda p: p.stem)
def test_rule_sections_present(path):
    text = body(path)
    positions = [text.find(s) for s in SECTIONS]
    assert all(p >= 0 for p in positions), f"{path.name}: missing {[s for s, p in zip(SECTIONS, positions) if p < 0]}"
    assert positions == sorted(positions), f"{path.name}: sections out of order"


def test_load_rules_rejects_bad_frontmatter(tmp_path):
    kb = load_kb()
    (tmp_path / "broken.md").write_text("---\nid: broken\nreqs: ru:x\n---\n## Why\n", encoding="utf-8")
    with pytest.raises(kb.KbError):
        kb.load_rules(str(tmp_path))


def test_load_rules_rejects_id_that_differs_from_file_name(tmp_path):
    kb = load_kb()
    text = ("---\nid: other\ntitle_ru: Т\ntitle_en: T\nreqs: [ru:x]\nbasis: norm\nfeatures: [forms.contact]\n"
            "always: false\nproducts: []\nstacks: []\n---\n## Why\n")
    (tmp_path / "one.md").write_text(text, encoding="utf-8")
    with pytest.raises(kb.KbError):
        kb.load_rules(str(tmp_path))


# --------------------------------------------------------------------------
# scripts/rules.py
# --------------------------------------------------------------------------

FIX_RULES = Path(__file__).resolve().parent / "fixtures" / "rules"
FIX_KB = Path(__file__).resolve().parent / "fixtures" / "scripts" / "kb"


def select_out(applicable, features=(), planned=(), products=("site",)):
    return {"inputs": {"features": list(features), "planned": list(planned), "products": list(products)},
            "applicable": [{"id": i, "why": ["always"]} for i in applicable]}


def run_rules(tmp_path, select_data, *extra):
    import subprocess
    path = tmp_path / "select.json"
    path.write_text(json.dumps(select_data), encoding="utf-8")
    return subprocess.run([sys.executable, str(SCRIPTS / "rules.py"), "--select", str(path), "--kb", str(FIX_KB),
                           "--rules", str(FIX_RULES), "--today", "2026-10-24", "--version", "0.2.0", *map(str, extra)],
                          capture_output=True, text=True)


def rule_lines(out):
    return [line for line in out.splitlines() if line.startswith("- ")]


def test_rules_cli_help_exits_0():
    import subprocess
    result = subprocess.run([sys.executable, str(SCRIPTS / "rules.py"), "--help"], capture_output=True, text=True)
    assert result.returncode == 0 and "--select" in result.stdout


def test_rules_picks_only_rules_with_applicable_requirements(tmp_path):
    # Review focus 4: a self-employed owner — select did not return ru:t-npd-only, so its rule is absent
    result = run_rules(tmp_path, select_out(["ru:t-always"], planned=["payments.yookassa"]))
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "Policy is published" not in out  # default lang ru
    assert "Политика опубликована" in out and "Чек самозанятого" not in out


def test_rules_needs_a_feature_or_always(tmp_path):
    out = run_rules(tmp_path, select_out(["ru:t-always", "ru:t-analytics"])).stdout
    assert "Счётчики после согласия" not in out  # requirement applicable, feature absent
    out = run_rules(tmp_path, select_out(["ru:t-always", "ru:t-analytics"], planned=["analytics.web_counter"])).stdout
    assert "Счётчики после согласия" in out


def test_rules_respect_products(tmp_path):
    assert "Два действия в боте" not in run_rules(tmp_path, select_out(["ru:t-always"])).stdout
    assert "Два действия в боте" in run_rules(tmp_path, select_out(["ru:t-always"], products=["bot"])).stdout


def test_rules_output_is_byte_identical_for_same_inputs(tmp_path):
    # Review focus 3: state.json compares sha256, so a rerun with the same inputs must not differ
    data = select_out(["ru:t-always", "ru:t-analytics", "ru:t-lowconf"], features=["analytics.web_counter"])
    first, second = run_rules(tmp_path, data).stdout, run_rules(tmp_path, data).stdout
    assert first == second and first


def test_rules_never_exceeds_max_lines(tmp_path):
    data = select_out(["ru:t-always", "ru:t-analytics", "ru:t-lowconf", "ru:t-ios"], features=["analytics.web_counter"])
    out = run_rules(tmp_path, data, "--max-lines", "5").stdout
    lines = out.rstrip("\n").splitlines()
    assert len(lines) <= 5
    assert "ещё" in lines[-1] and "plan.md" in lines[-1]


def test_rules_default_limit_is_60_lines(tmp_path):
    out = run_rules(tmp_path, select_out(["ru:t-always"])).stdout
    assert len(out.rstrip("\n").splitlines()) <= 60


def test_rules_label_downgrades_norm_for_low_confidence_requirement(tmp_path):
    out = run_rules(tmp_path, select_out(["ru:t-lowconf", "ru:t-always"])).stdout
    weak = [l for l in rule_lines(out) if "Слабая норма" in l][0]
    strong = [l for l in rule_lines(out) if "Политика опубликована" in l][0]
    assert "трактовка" in weak and "норма" not in weak.split("—", 1)[1].replace("Слабая норма", "")
    assert ", норма" in strong


def test_rules_platform_label_for_store_policy(tmp_path):
    out = run_rules(tmp_path, select_out(["ru:t-ios"], products=["ios"])).stdout
    line = [l for l in rule_lines(out) if "Удаление аккаунта" in l][0]
    assert "правило платформы" in line


def test_rules_lines_cite_requirements_and_order_norm_first(tmp_path):
    data = select_out(["ru:t-always", "ru:t-analytics", "ru:t-lowconf"], features=["analytics.web_counter"])
    lines = rule_lines(run_rules(tmp_path, data).stdout)
    assert all("ru:t-" in l for l in lines)
    assert "Политика опубликована" in lines[0]


def test_rules_output_has_no_absolute_paths(tmp_path):
    data = select_out(["ru:t-always", "ru:t-analytics"], features=["analytics.web_counter"])
    out = run_rules(tmp_path, data, "--stacks", "nextjs").stdout
    assert "/Us" + "ers/" not in out and "~" not in out and " /" not in out
    assert "legal-kit references/stacks/nextjs.md" in out


def test_rules_english_titles_with_lang_en(tmp_path):
    out = run_rules(tmp_path, select_out(["ru:t-always"]), "--lang", "en").stdout
    assert "Policy is published" in out and "norm" in out and "Generated by legal-kit 0.2.0" in out


def test_rules_bad_select_exits_2(tmp_path):
    import subprocess
    bad = tmp_path / "select.json"
    bad.write_text("[]", encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPTS / "rules.py"), "--select", str(bad), "--kb", str(FIX_KB),
                             "--rules", str(FIX_RULES)], capture_output=True, text=True)
    assert result.returncode == 2
