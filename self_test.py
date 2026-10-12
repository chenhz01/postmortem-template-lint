# -*- coding: utf-8 -*-
"""self_test for postmortem-template-lint — R14, inherits 4-defence template v2.

Defence 1: run_cli captures SystemExit/BaseException from argparse main().
Defence 2: no ASCII-only \\w+ on non-ASCII fixture content.
Defence 3: fixtures written with newline="" to avoid \\r\\n double-write.
Defence 4: last line is `SUMMARY: PASS n/n`.
"""
import atexit
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="\n")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import postmortem_template_lint as m  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="pmlint_selftest_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)


def wf(name, content):
    """Defence 3: write fixture with newline='' (no CRLF double-write)."""
    p = os.path.join(_TMP, name)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return p


def run_cli(argv):
    """Defence 1: catch SystemExit and Exception; return (code, stdout, stderr)."""
    buf_out, buf_err = io.StringIO(), io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            m.main(argv)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:  # noqa: BLE001
        code = 1
        buf_err.write(repr(e))
    return code, buf_out.getvalue(), buf_err.getvalue()


def compose(impact=None, timeline=None, root=None, actions=None):
    out = ["# Incident 2026-10-01: API outage"]
    if impact is not None:
        out.append("## Impact\n%s" % impact)
    if timeline is not None:
        out.append("## Timeline\n%s" % timeline)
    if root is not None:
        out.append("## Root Cause\n%s" % root)
    if actions is not None:
        out.append("## Action Items\n%s" % actions)
    return "\n\n".join(out) + "\n"


D_IMPACT = "About 12 minutes of elevated error rates for the checkout API."
D_TIMELINE = "- 09:00 deploy v123 to production\n- 09:07 first error alerts fired\n- 09:19 rollback completed"
D_ROOT = ("A config change removed the retry budget, so a slow dependency "
          "cascaded into timeouts across the connection pool.")
D_ACTIONS = "- [ ] Restore retry budget defaults @owner: sre\n- [ ] Add config canary @owner: platform"
GOOD = compose(D_IMPACT, D_TIMELINE, D_ROOT, D_ACTIONS)
BLAMEY = compose(D_IMPACT, D_TIMELINE,
                 D_ROOT + " She failed to check the canary.", D_ACTIONS)

TPL_BAD_JSON = wf("b_tpl_bad.json", "{oops not json")
TPL_WRONG_SCHEMA = wf("b_tpl_wrong.json", json.dumps({"required_sections": 5}))

# ---- [A] functional: (name, text, checks [(code, msg_sub)], no_errors) ----
A_CASES = [
    ("full_report_clean", GOOD, [], True),
    ("missing_timeline", compose(D_IMPACT, None, D_ROOT, D_ACTIONS), [("MISSING_SECTION", "Timeline")], False),
    ("missing_rootcause", compose(D_IMPACT, D_TIMELINE, None, D_ACTIONS), [("MISSING_SECTION", "Root Cause")], False),
    ("missing_actions", compose(D_IMPACT, D_TIMELINE, D_ROOT, None), [("MISSING_SECTION", "Action Items")], False),
    ("missing_impact", compose(None, D_TIMELINE, D_ROOT, D_ACTIONS), [("MISSING_SECTION", "Impact")], False),
    ("custom_template_extra", GOOD, [("MISSING_SECTION", "Lessons Learned")], False, {"required_sections": ["Timeline", "Root Cause", "Action Items", "Impact", "Lessons Learned"]}),
    ("custom_template_minimal", GOOD, [], True, {"required_sections": ["Timeline"]}),
    ("blame_person", "she failed to check the config", [("BLAME_PERSON_VERB", "")], False),
    ("blame_possession", "it was her fault", [("BLAME_POSSESSION", "")], False),
    ("blame_character", "the deploy was sloppy", [("BLAME_CHARACTER", "")], False),
    ("blame_punitive", "he should be fired for this", [("BLAME_PUNITIVE", "")], False),
    ("blame_human_error", "root cause was human error", [("BLAME_HUMAN_ERROR", "")], False),
    ("action_no_owner", compose(actions="- [ ] add alerting\n- [ ] fix runbook @owner: sre"),
     [("ACTION_NO_OWNER", "#1")], False),
    ("actions_empty", compose(actions=""), [("NO_ACTION_ITEMS", "")], False),
    ("timeline_empty", compose(timeline=""), [("EMPTY_TIMELINE", "")], False),
    ("timeline_no_ts", compose(timeline="- deploy went out\n- alerts fired"), [("TIMELINE_NO_TS", "#1")], False),
    ("timeline_iso_ok", compose(D_IMPACT, "- 2026-10-01 deploy\n- 2026-10-01 rollback", D_ROOT, D_ACTIONS), [], True),
    ("root_empty", compose(root=""), [("EMPTY_ROOT_CAUSE", "")], False),
    ("root_thin", compose(root="database died"), [("THIN_ROOT_CAUSE", "")], False),
]


def _mk_a(name, text, checks, no_errors, template=None):
    def t(self):
        fs = m.lint_postmortem(text, template)
        if no_errors:
            self.assertEqual([f for f in fs if f["severity"] == "ERROR"], [], msg=name)
        for code, sub in checks:
            hit = [f for f in fs if f["code"] == code and sub in f["message"]]
            self.assertTrue(hit, msg="%s expects %s (%r)" % (name, code, sub))
    t.__doc__ = "A: %s" % name
    return t


class TestA(unittest.TestCase):
    def test_a20_missing_severity_is_error(self):
        fs = m.lint_postmortem(compose(D_IMPACT, None, D_ROOT, D_ACTIONS))
        self.assertEqual(fs[0]["severity"], "ERROR")

    def test_a21_blame_location_is_line(self):
        fs = m.lint_postmortem("she broke it")
        bl = [f for f in fs if f["code"] == "BLAME_PERSON_VERB"][0]
        self.assertTrue(bl["location"].startswith("line"))

    def test_a22_blame_score_counts(self):
        self.assertEqual(m.blame_score("she failed. they broke stuff."), 2)

    def test_a23_case_insensitive_sections(self):
        text = "# incident\n\n## timeline\n- 09:00 x\n\n## root cause\nenough root cause text here for the check.\n\n## action items\n- [ ] fix @owner: sre\n\n## impact\nlow\n"
        self.assertEqual([f for f in m.lint_postmortem(text) if f["severity"] == "ERROR"], [])

    def test_a24_template_invalid_raises(self):
        with self.assertRaises(ValueError):
            m.lint_postmortem(GOOD, {"required_sections": "nope"})

    def test_a25_unicode_content_ok(self):
        text = compose("影响：12 分钟错误率升高。", "- 09:00 部署\n- 09:07 告警", D_ROOT, D_ACTIONS)
        self.assertEqual([f for f in m.lint_postmortem(text) if f["severity"] == "ERROR"], [])


for _i, _c in enumerate(A_CASES):
    _nm, _txt, _ck, _ne = _c[0], _c[1], _c[2], _c[3]
    _tp = _c[4] if len(_c) > 4 else None
    setattr(TestA, "test_a%02d_%s" % (_i, _nm), _mk_a(_nm, _txt, _ck, _ne, _tp))

# ---- [B] CLI contract: (name, content|None, extra_args, code, out_sub, err_sub) ----
B_CASES = [
    ("clean_exit0", GOOD, [], 0, "", ""),
    ("bad_exit1", "just text, no sections at all", [], 1, "", ""),
    ("json_flag", GOOD, ["--json"], 0, '"findings"', ""),
    ("missing_file", None, [], 2, "", "cannot read"),
    ("template_missing", GOOD, ["--template", "definitely_absent.json"], 2, "", "cannot load"),
    ("template_bad_json", GOOD, ["--template", TPL_BAD_JSON], 2, "", "cannot load"),
    ("template_wrong_schema", GOOD, ["--template", TPL_WRONG_SCHEMA], 2, "", "error"),
    ("strict_warn_exit1", BLAMEY, ["--strict"], 1, "", ""),
    ("warn_without_strict_exit0", BLAMEY, [], 0, "", ""),
    ("text_output_summary", GOOD, [], 0, "summary:", ""),
    ("json_summary_key", GOOD, ["--json"], 0, '"summary"', ""),
    ("max_blame_zero", BLAMEY, ["--max-blame", "0"], 1, "", ""),
    ("max_blame_high", BLAMEY, ["--max-blame", "99"], 0, "", ""),
]


def _mk_b(name, content, extra, code, out_sub="", err_sub=""):
    def t(self):
        if content is None:
            argv = [os.path.join(_TMP, "absent_%s.md" % name)] + extra
        else:
            argv = [wf("b_%s.md" % name, content)] + extra
        c, out, err = run_cli(argv)
        self.assertEqual(c, code, msg="out=%r err=%r" % (out, err))
        if out_sub:
            self.assertIn(out_sub, out)
        if err_sub:
            self.assertIn(err_sub, err)
    t.__doc__ = "B: %s" % name
    return t


class TestB(unittest.TestCase):
    def test_b13_missing_positional(self):
        c, _out, _err = run_cli([])
        self.assertEqual(c, 2)

    def test_b14_help_exit0(self):
        c, out, _err = run_cli(["--help"])
        self.assertEqual(c, 0)
        self.assertIn("usage:", out)


for _i, (_nm, _ct, _ex, _cd, _os, _es) in enumerate(B_CASES):
    setattr(TestB, "test_b%02d_%s" % (_i, _nm), _mk_b(_nm, _ct, _ex, _cd, _os, _es))

# ---- [C] extreme/edge: (name, fn(self)) ----
C_CASES = [
    ("empty_text", lambda s: s.assertEqual(
        len([f for f in m.lint_postmortem("") if f["code"] == "MISSING_SECTION"]), 4)),
    ("whitespace_only", lambda s: s.assertEqual(
        len([f for f in m.lint_postmortem("   \n\t  ") if f["code"] == "MISSING_SECTION"]), 4)),
    ("headings_only", lambda s: s.assertTrue(
        {"EMPTY_TIMELINE", "EMPTY_ROOT_CAUSE", "NO_ACTION_ITEMS"} <=
        {f["code"] for f in m.lint_postmortem("# t\n\n## Timeline\n\n## Root Cause\n\n## Action Items\n\n## Impact\n")})),
    ("unicode_body_no_error", lambda s: s.assertEqual(
        [f for f in m.lint_postmortem(compose("影响：12 分钟 😱", D_TIMELINE, D_ROOT, D_ACTIONS))
         if f["severity"] == "ERROR"], [])),
    ("emoji_in_body", lambda s: s.assertIsInstance(
        m.lint_postmortem(compose(impact="12 min \U0001F631 downtime")), list)),
    ("crlf_same_codes", lambda s: s.assertEqual(
        sorted(f["code"] for f in m.lint_postmortem(GOOD.replace("\n", "\r\n"))),
        sorted(f["code"] for f in m.lint_postmortem(GOOD)))),
    ("huge_report_clean", lambda s: s.assertEqual(
        m.lint_postmortem(compose(impact="x" * 200000, timeline=D_TIMELINE, root=D_ROOT, actions=D_ACTIONS)), [])),
    ("blame_100_hits", lambda s: s.assertEqual(m.blame_score("she failed\n" * 100), 100)),
    ("word_boundary_no_hit", lambda s: s.assertEqual(
        m.blame_score("they failedX and she failedy"), 0)),
    ("h4_heading_still_missing", lambda s: s.assertTrue(any(
        f["code"] == "MISSING_SECTION" and "Timeline" in f["message"]
        for f in m.lint_postmortem("# t\n\n#### Timeline\n- 09:00 x\n\n#### Root Cause\nlong enough root cause text here.\n\n#### Action Items\n- [ ] a @owner: x\n\n#### Impact\nlow\n")))),
    ("duplicate_sections_first_wins", lambda s: s.assertEqual(
        [f for f in m.lint_postmortem(GOOD + "\n## Timeline\n- 10:00 more\n")
         if f["severity"] == "ERROR"], [])),
    ("template_empty_list_no_missing", lambda s: s.assertEqual(
        m.lint_postmortem(GOOD, {"required_sections": []}), [])),
    ("template_unicode_section", lambda s: s.assertTrue(any(
        "复盘" in f["message"] for f in
        m.lint_postmortem(GOOD, {"required_sections": ["复盘"]})))),
    ("type_none_raises", lambda s: s.assertRaises(TypeError, m.lint_postmortem, None)),
    ("type_int_raises", lambda s: s.assertRaises(TypeError, m.lint_postmortem, 123)),
    ("template_list_raises", lambda s: s.assertRaises(ValueError, m.lint_postmortem, GOOD, ["a"])),
    ("template_str_raises", lambda s: s.assertRaises(ValueError, m.lint_postmortem, GOOD, "nope")),
    ("cli_empty_file_exit1", lambda s: s.assertEqual(
        run_cli([wf("c_empty.md", "")])[0], 1)),
    ("cli_directory_exit2", lambda s: s.assertEqual(run_cli([_TMP])[0], 2)),
    ("timeline_tab_indent_ok", lambda s: s.assertEqual(
        [f for f in m.lint_postmortem(compose(D_IMPACT, "  - 09:00 deploy", D_ROOT, D_ACTIONS))
         if f["severity"] == "ERROR"], [])),
    ("single_digit_hour_ok", lambda s: s.assertEqual(
        [f for f in m.lint_postmortem(compose(timeline="- 9:07 alerts"))
         if f["code"] == "TIMELINE_NO_TS"], [])),
    ("blame_case_insensitive", lambda s: s.assertTrue(any(
        f["code"] == "BLAME_PERSON_VERB" for f in m.lint_postmortem("SHE FAILED the check")))),
    ("blame_found_in_any_section", lambda s: s.assertTrue(any(
        f["code"] == "BLAME_PERSON_VERB"
        for f in m.lint_postmortem(compose(root="Config was fine; she broke the dashboard."))))),
    ("multiple_no_owner_findings", lambda s: s.assertEqual(
        len([f for f in m.lint_postmortem(compose(actions="- [ ] a\n- [ ] b"))
             if f["code"] == "ACTION_NO_OWNER"]), 2)),
    ("very_long_single_line", lambda s: s.assertIsInstance(
        m.lint_postmortem(compose(root="cause " * 10000)), list)),
    ("cli_json_roundtrip", lambda s: s.assertEqual(
        json.loads(run_cli([wf("c_rt.md", GOOD), "--json"])[1])["summary"]["error"], 0)),
]


class TestC(unittest.TestCase):
    pass


for _i, (_nm, _fn) in enumerate(C_CASES):
    setattr(TestC, "test_c%02d_%s" % (_i, _nm), _fn)


# ---- Round-2 additions (v0.1.1): extra extreme-edge coverage ----
class TestR2(unittest.TestCase):
    def test_r2_blame_inside_timeline(self):
        fs = m.lint_postmortem(compose(D_IMPACT, "- 09:00 she failed to deploy\n- 09:07 alerts", D_ROOT, D_ACTIONS))
        self.assertTrue(any(f["code"] == "BLAME_PERSON_VERB" for f in fs))

    def test_r2_template_duplicate_names(self):
        self.assertEqual(m.lint_postmortem(GOOD, {"required_sections": ["Timeline", "Timeline"]}), [])

    def test_r2_crlf_blame_score(self):
        self.assertEqual(m.blame_score("she failed\r\nher fault\r\n"), 2)

    def test_r2_bom_file_exit0(self):
        c, _o, _e = run_cli([wf("r2_bom.md", "\ufeff" + GOOD)])
        self.assertEqual(c, 0)

if __name__ == "__main__":
    r = unittest.TextTestRunner(verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules["__main__"]))
    total, fails = r.testsRun, len(r.failures) + len(r.errors)
    print("SUMMARY: PASS %d/%d" % (total - fails, total))  # Defence 4
    sys.exit(0 if fails == 0 else 1)
