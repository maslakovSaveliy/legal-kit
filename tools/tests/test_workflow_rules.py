"""Rules of the workflow files that the evals showed missing or unclear (iteration 4).

Each test pins one sentence-level rule; the wording may change, the pinned terms may not.
"""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "skills" / "legal-kit"
WORKFLOW = SKILL / "references" / "workflow"
SKILL_MD = SKILL / "SKILL.md"
RU = SKILL / "references" / "jurisdictions" / "ru"


def read(name):
    return (WORKFLOW / name).read_text(encoding="utf-8")


def section(text, heading):
    start = text.index("\n## " + heading + "\n")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else None]


def test_passage_kept_only_when_confirmed_is_left_out_of_the_public_page():
    rule = section(read("documents.md"), "Drafts and public pages") if "\n## Drafts and public pages\n" in read(
        "documents.md") else read("documents.md")
    assert "«Заполняйте, только если" in rule and "«оставляйте, только если" in rule
    assert "«Заполняйте только после" in rule and "«… только если это сделано»" in rule  # cookie notice wording
    assert "`{{РЕГИОН_РАЗМЕЩЕНИЯ_БД}}`" in rule and "left out of the public page" in rule
    assert "a heading left without text goes too" in rule


def test_every_fill_only_if_note_of_the_templates_is_named_by_the_rule():
    import re
    templates = SKILL / "references" / "jurisdictions" / "ru" / "templates"
    notes = set()
    for path in templates.glob("*/text.md"):
        notes |= {m.group(1) for m in re.finditer(r"\[(Заполняйте,? только [а-яё]+|[Оо]ставляйте, только если)", path.read_text(encoding="utf-8"))}
    rule = read("documents.md")
    assert notes and all(("«" + n[0].upper() + n[1:]) in rule or ("«" + n) in rule for n in notes), notes


def test_row_date_falls_back_to_the_record_date_when_the_cited_norm_has_none():
    for name in ("report.md", "applicability.md"):
        text = read(name)
        assert "no date in `norm_dates`" in text and "the record's `effective_from`" in text, name


def test_manual_verify_checks_that_every_applicable_id_has_a_row():
    manual = section(read("report.md"), "Without python3")
    assert "every id of `applicable`" in manual and "uncovered_req" in read("report.md")


def test_manual_select_json_has_a_shape():
    manual = section(read("applicability.md"), "Without python3")
    for key in ('"applicable"', '"why"', '"not_applicable"', '"templates"', '"documents"', '"not_detectable"'):
        assert key in manual, key


def test_manual_inn_and_ogrn_check_digits_are_spelled_out():
    manual = section(read("documents.md"), "Without python3")
    assert "_kb.py" not in manual
    for weights in ("2, 4, 10, 3, 5, 9, 4, 6, 8", "7, 2, 4, 10, 3, 5, 9, 4, 6, 8", "3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8"):
        assert weights in manual, weights
    assert "mod 11 mod 10" in manual and "mod 13 mod 10" in manual


def test_manual_render_gives_the_row_table():
    manual = section(read("report.md"), "Without python3")
    assert "| Требование | Статус | Уровень | Норма | Уверенность | Источник | Доказательства |" in manual


def test_cards_disputed_section_is_read_for_every_assessed_requirement():
    text = read("applicability.md")
    assert '--section "Пробелы и спорные места"' in text and "except those you mark `n_a`" in text
    assert "kb.py card ru:<a> ru:<b>" in text


def test_verify_is_run_with_select_in_every_mode():
    assert "[--select" not in read("report.md") and "--select .legal/evidence/select.json" in read("report.md")
    skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "with `--answers .legal/answers.json` and `--select .legal/evidence/select.json`" in skill


# Rules the live run on a Tilda site with a foreign owner showed missing or unclear.

def subsection(text, heading):
    start = text.index("\n### " + heading + "\n")
    ends = [i for i in (text.find("\n### ", start + 1), text.find("\n## ", start + 1)) if i != -1]
    return text[start:min(ends) if ends else None]


def skill_text():
    return (SKILL / "SKILL.md").read_text(encoding="utf-8")


def test_foreign_owner_skips_russian_registries_by_identifier():
    rule = section(read("recon-prod.md"), "Public registries")
    assert "`egrul`, `npd` and `cbr` never run, with or without an INN" in rule
    assert "never for a `foreign` owner" in rule and "by name" in rule and "`owner.reg_number`" in rule
    assert "«ЕГРЮЛ не проверялся: иностранная компания»" in rule


def test_foreign_owner_identifiers_replace_inn_and_ogrn_in_drafts():
    rule = subsection(read("documents.md"), "Placeholders")
    assert "`foreign`" in rule and "`{{СТРАНА_РЕГИСТРАЦИИ}}`" in rule and "`{{РЕГИСТРАЦИОННЫЙ_НОМЕР}}`" in rule
    assert "«страна регистрации {{СТРАНА_РЕГИСТРАЦИИ}}, регистрационный номер {{РЕГИСТРАЦИОННЫЙ_НОМЕР}}»" in rule
    assert "`owner.reg_number`" in rule and "`owner.country`" in rule and "«по ЕГРЮЛ» is dropped" in rule
    assert "a bare `{{ОГРН_ИЛИ_ОГРНИП}}`" in rule and "`РЕГИСТРАЦИОННЫЙ_НОМЕР` in `owner.withheld`" in rule
    schema = (SKILL / "references" / "jurisdictions" / "ru" / "owner-questions.md").read_text(encoding="utf-8")
    assert any(line.strip().startswith('"reg_number"') for line in schema.splitlines())


def test_unknown_requisite_is_not_withheld():
    assert "is not withholding" in skill_text()
    rule = subsection(read("documents.md"), "Drafts and public pages")
    assert "«не знаю»" in rule and "unavailable" in rule and "never adds" in rule
    assert "points to the policy page the site already has" in rule
    assert "nothing goes into `owner.withheld`" in read("intake.md")


def test_long_disputed_sections_go_to_an_evidence_file_and_are_all_read():
    rule = read("applicability.md")
    assert "`.legal/evidence/disputed-sections.md`" in rule
    assert "every section in it is read" in rule


def test_suggestions_row_condition_is_the_same_in_skill_and_report():
    line = next(line for line in skill_text().splitlines() if "«Предложения скилла»" in line)
    assert "only when" in line and "reached a public page" in line
    assert "stays in the drafts gets no" in read("report.md")


def test_no_repo_step_points_to_the_no_code_guide():
    line = next(line for line in skill_text().splitlines() if line.startswith("- No repo or a no-code site"))
    assert "references/stacks/no-code.md" in line
    guide = (SKILL / "references" / "stacks" / "no-code.md").read_text(encoding="utf-8")
    assert "`data-tilda-cookie-type`" in guide


def test_bad_checksum_keeps_the_page_a_draft():
    text = read("documents.md")
    assert "fails its check digit" in text and "stays a draft" in text
    assert "| `inn_checksum`, `ogrn_checksum` | on a public page |" in text


def test_project_tests_run_only_against_a_local_database():
    rule = "tests that need a database run only when its configured host is local"
    assert rule in read("safety.md") and rule in read("ui-integration.md")


def test_cms_placement_is_left_to_the_user():
    text = read("ui-integration.md")
    assert "computer use" not in text and "The user places them" in text


def test_owner_country_may_be_unknown_and_recon_signals_reach_the_block():
    questions = (RU / "owner-questions.md").read_text(encoding="utf-8")
    intake = read("intake.md")
    assert '"country": "string | null' in questions
    assert "found in recon" in intake and "the country is a blocking part of item 3" in intake


def test_listing_only_app_and_repo_less_bot_run_as_prod_only():
    intake, safety = read("intake.md"), read("safety.md")
    mode = intake[intake.index("### Mode"):intake.index("### Git tree")]
    assert "only a store listing" in mode and "only a bot link" in mode and "`prod-only`" in mode
    assert "never sends a message to a live bot" in safety
    assert "never sends a message to a live bot" in (SKILL / "references" / "stacks" / "bot.md").read_text(encoding="utf-8")


def test_left_out_passages_do_not_hold_a_page_back():
    for name in ("ui-integration.md", "documents.md"):
        assert "passages left out under" in read(name), name
    assert "a passage left out for an unknown fact does not hold the page" in SKILL_MD.read_text(encoding="utf-8")


def test_feature_mode_skips_the_start_gate_and_scans_the_code():
    feature = section(read("plan.md"), "Feature mode")
    assert "Mode `feature` skips this gate" in SKILL_MD.read_text(encoding="utf-8")
    assert "scan_repo.py" in feature and ".legal/evidence/select-rules.json" in feature


def test_state_kinds_are_one_list():
    skill = SKILL_MD.read_text(encoding="utf-8")
    row = next(line for line in skill.splitlines() if line.startswith("| `state.json` |"))
    table = read("ui-integration.md")
    for kind in ("page", "checkbox", "banner", "footer", "consent-log", "rules", "agent-link"):
        assert "`%s`" % kind in row, kind
        assert "| `%s` |" % kind in table, kind


def test_scripts_table_matches_the_scripts_folder():
    skill = SKILL_MD.read_text(encoding="utf-8")
    for script in sorted(p.name for p in (SKILL / "scripts").glob("*.py") if not p.name.startswith("_")):
        assert "| `scripts/%s" % script in skill, script
    assert "All print JSON (except `render`)" not in skill  # rules.py and kb.py card print Markdown, kb.py extract writes


def test_small_lists_are_current():
    assert "':(exclude).legal'" in section(read("intake.md"), "Without python3")
    kinds_line = next(line for line in (RU / "JURISDICTION.md").read_text(encoding="utf-8").splitlines()
                      if "product kinds" in line)
    assert "`bot`" in kinds_line
    assert "registry.py egrul|npd|whois|cbr|rkn" in (RU / "registries.md").read_text(encoding="utf-8")


def test_swift_build_runs_only_with_packages_already_fetched():
    text = (SKILL / "references" / "stacks" / "swift.md").read_text(encoding="utf-8")
    line = next(line for line in text.splitlines() if "xcodebuild -scheme" in line)
    assert "already fetched" in line and "not_checked" in line


def test_platform_pages_are_read_not_crawled():
    intake = read("intake.md")
    mode = intake[intake.index("### Mode"):intake.index("### Git tree")]
    assert "do not crawl" in mode
