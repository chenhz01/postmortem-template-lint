# -*- coding: utf-8 -*-
"""postmortem-template-lint: blameless postmortem report linter (pure stdlib).

Checks a markdown postmortem for required sections (Timeline, Root Cause,
Action Items, Impact by default), flags blame-oriented language, verifies
that action items declare owners and timeline entries carry timestamps.
"""
import argparse
import json
import re
import sys

__version__ = "0.1.1"

DEFAULT_REQUIRED_SECTIONS = ["Timeline", "Root Cause", "Action Items", "Impact"]

BLAME_PATTERNS = [
    ("BLAME_PERSON_VERB",
     re.compile(r"\b(?:he|she|they)\s+(?:failed|broke|forgot|ignored|misconfigured)\b", re.I),
     "person-directed blame phrasing"),
    ("BLAME_POSSESSION",
     re.compile(r"\b(?:his|her|their)\s+(?:fault|mistake|carelessness|negligence)\b", re.I),
     "possession-of-fault phrasing"),
    ("BLAME_CHARACTER",
     re.compile(r"\b(?:sloppy|lazy|incompetent|careless|stupid|clueless)\b", re.I),
     "character-attack wording"),
    ("BLAME_PUNITIVE",
     re.compile(r"\bshould\s+(?:be|have\s+been)\s+(?:fired|blamed|punished|disciplined)\b", re.I),
     "punitive phrasing"),
    ("BLAME_HUMAN_ERROR",
     re.compile(r"\b(?:human|operator)\s+error\b", re.I),
     "single-cause 'human error' phrasing; prefer systemic framing"),
]

SECTION_RE = re.compile(r"^#{1,3}\s*(.+?)\s*$", re.M)
TS_RE = re.compile(r"(?:\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2})")


def find_sections(text):
    """Return {lower_title: body} for markdown headings of level 1-3."""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    sections = {}
    matches = list(SECTION_RE.finditer(text))
    for i, mt in enumerate(matches):
        title = mt.group(1).strip().lower()
        start = mt.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.setdefault(title, text[start:end])
    return sections


def _find_body(sections, *needles):
    for key, body in sections.items():
        if all(n in key for n in needles):
            return body
    return None


def blame_score(text):
    """Count total blame-pattern hits in the text."""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    return sum(1 for _code, rx, _msg in BLAME_PATTERNS for _ in rx.finditer(text))


def lint_postmortem(text, template=None):
    """Lint a postmortem report, returning a list of finding dicts.

    Each finding: {code, severity (ERROR/WARN/INFO), message, location}.
    Raises TypeError for non-str text, ValueError for a malformed template.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    findings = []

    def add(code, sev, msg, loc):
        findings.append({"code": code, "severity": sev, "message": msg, "location": loc})

    required = list(DEFAULT_REQUIRED_SECTIONS)
    if template is not None:
        if (not isinstance(template, dict)
                or not isinstance(template.get("required_sections"), list)
                or not all(isinstance(s, str) and s.strip()
                           for s in template["required_sections"])):
            raise ValueError('template must be {"required_sections": [str, ...]}')
        required = template["required_sections"]

    sections = find_sections(text)

    for name in required:
        if name.strip().lower() not in sections:
            add("MISSING_SECTION", "ERROR",
                "required section missing: %s" % name, name)

    for code, rx, msg in BLAME_PATTERNS:
        for lm in rx.finditer(text):
            line = text.count("\n", 0, lm.start()) + 1
            add(code, "WARN", "%s: %r" % (msg, lm.group(0)), "line %d" % line)

    ai_body = _find_body(sections, "action", "item")
    if ai_body is not None:
        items = [ln for ln in ai_body.splitlines()
                 if ln.strip().startswith(("-", "*"))]
        if not items:
            add("NO_ACTION_ITEMS", "ERROR",
                "Action Items section has no items", "Action Items")
        for idx, ln in enumerate(items, 1):
            low = ln.lower()
            if "@owner" not in low and "owner:" not in low and "owner @" not in low:
                add("ACTION_NO_OWNER", "WARN",
                    "action item #%d has no owner" % idx, "Action Items")

    tl_body = _find_body(sections, "timeline")
    if tl_body is not None:
        entries = [ln.strip() for ln in tl_body.splitlines()
                   if ln.strip().startswith(("-", "*"))]
        if not entries:
            add("EMPTY_TIMELINE", "ERROR",
                "Timeline section has no entries", "Timeline")
        for idx, ln in enumerate(entries, 1):
            if not TS_RE.search(ln):
                add("TIMELINE_NO_TS", "WARN",
                    "timeline entry #%d lacks timestamp" % idx, "Timeline")

    rc_body = _find_body(sections, "root cause")
    if rc_body is not None:
        stripped = rc_body.strip()
        if not stripped:
            add("EMPTY_ROOT_CAUSE", "ERROR",
                "Root Cause section is empty", "Root Cause")
        elif len(stripped) < 20:
            add("THIN_ROOT_CAUSE", "WARN",
                "Root Cause section is very short (<20 chars)", "Root Cause")
    return findings


def summarize(findings):
    """Return {error, warn, info} counts for a finding list."""
    out = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        key = f["severity"].lower()
        out[key] = out.get(key, 0) + 1
    return out


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="postmortem-template-lint",
        description="Lint blameless postmortem reports: required sections, "
                    "blame language, owner/timestamp hygiene.")
    p.add_argument("report", help="path to the postmortem markdown report")
    p.add_argument("--template", default=None,
                   help='JSON file: {"required_sections": [...]}')
    p.add_argument("--json", dest="as_json", action="store_true",
                   help="emit findings as JSON")
    p.add_argument("--strict", action="store_true",
                   help="WARN findings also cause exit code 1")
    p.add_argument("--max-blame", type=int, default=None, dest="max_blame",
                   help="fail when blame-pattern hits exceed this number")
    a = p.parse_args(argv)

    try:
        with open(a.report, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print("error: cannot read report: %s" % e, file=sys.stderr)
        sys.exit(2)

    template = None
    if a.template:
        try:
            with open(a.template, "r", encoding="utf-8") as f:
                template = json.load(f)
        except (OSError, ValueError) as e:
            print("error: cannot load template: %s" % e, file=sys.stderr)
            sys.exit(2)

    try:
        findings = lint_postmortem(text, template)
    except (TypeError, ValueError) as e:
        print("error: %s" % e, file=sys.stderr)
        sys.exit(2)

    if a.max_blame is not None:
        bs = blame_score(text)
        if bs > a.max_blame:
            findings.append({"code": "BLAME_BUDGET", "severity": "ERROR",
                             "message": "blame hits %d exceed budget %d" % (bs, a.max_blame),
                             "location": "$"})

    s = summarize(findings)
    if a.as_json:
        print(json.dumps({"findings": findings, "summary": s},
                         ensure_ascii=False, indent=2))
    else:
        for f in findings:
            print("[%s] %s %s: %s" % (f["severity"], f["location"],
                                      f["code"], f["message"]))
        print("summary: %d error(s), %d warn(s), %d info(s)"
              % (s["error"], s["warn"], s["info"]))

    rc = 1 if (s["error"] or (a.strict and s["warn"])) else 0
    sys.exit(rc)


if __name__ == "__main__":
    main()
