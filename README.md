# postmortem-template-lint

A stdlib-only linter that checks blameless postmortem reports before you publish them. It verifies required sections (Timeline, Root Cause, Action Items, Impact), flags blame-oriented language, and catches action items without owners. If you ship incident reviews and want them consistent and blame-free, this is for you; otherwise skip it.

## Problem

Postmortems drift. Teams adopt a template, then reports quietly lose the timeline, action items lose owners, and blame language ("she failed", "human error") creeps back in — undermining the blameless culture the template was meant to enforce. Reviews catch this inconsistently, by hand, per reader.

## How it works

- Parses markdown headings (levels 1-3) into sections.
- Checks each required section exists (customizable via a JSON template: `{"required_sections": [...]}`).
- Scans the whole text against five blame-pattern regexes (person-directed verbs, possession-of-fault, character attacks, punitive phrasing, "human error") and reports line numbers.
- Validates that Action Items contain items with `@owner:` markers and Timeline entries carry timestamps (`HH:MM` or ISO dates).
- Emits findings as `{code, severity, message, location}`; exit code 1 on ERROR (or WARN under `--strict`).

## Quickstart (~2 min)

```bash
python postmortem_template_lint.py check my-incident.md            # ~0.2s
python postmortem_template_lint.py check my-incident.md --strict   # WARN also fails
python postmortem_template_lint.py check my-incident.md --template sections.json
```

Then run the self-test suite: `python self_test.py` (~0.6s).

## Why not X

No direct equivalent found as of 2026-10-13: searches for "blameless postmortem linter / postmortem template checker" surface writing guides (Google SRE book chapter, PagerDuty templates) and generic markdown linters, but no standalone, offline, template-driven postmortem validator. Nearest neighbors, and why they don't cover this:

- **markdownlint / mdl** — generic markdown style (heading order, line length); knows nothing about incident semantics, blame language, or owners.
- **Vale (prose linter)** — excellent style/word checks, but rule packs for blame language don't exist out of the box, and it has no notion of required report structure or action-item owners.
- **Incident-management platforms (PagerDuty, Jeli, FireHydrant)** — workflow products with baked-in templates; not an embeddable, dependency-free check you can run in CI on arbitrary markdown.
- **Custom grep one-liners** — the usual fallback; no severity model, no section logic, no exit-code contract.

## Performance

Measured on CPython 3.13.12, Windows 10 Pro, 2026-10-13:

- Full self-test suite (70 cases): **~0.6 s** [Measured] — repro: `python self_test.py`
- Lint a ~2.6 KB report: **~0.27 ms/op** [Measured] — repro:

```bash
python -m timeit -s "import postmortem_template_lint as m" "m.lint_postmortem(open('report.md', encoding='utf-8').read())"
```

## Minimal Fallback

No installs needed beyond Python 3.8+. If even importing the module is a problem, the same guarantees reduce to two greps:

```bash
grep -ciE "(he|she|they) (failed|broke)" report.md   # blame scan
grep -c "^## " report.md                              # section presence
```

You lose severity levels, owner/timestamp checks, and the exit-code contract.

## Design Trade-offs

- **Regex blame detection over NLP**: zero dependencies and fully explainable findings, at the cost of false negatives on subtle blame. We prioritized auditability and portability.
- **Section matching by substring** (`"timeline" in heading`): tolerates variant titles ("Detailed Timeline") but can over-match; we preferred tolerance over brittle exact matching.
- **Priority order in conflicts**: safety of the blameless culture > lint strictness > convenience; `--strict` is opt-in, never default.

## Limits & Second-order Effects

- Headings inside fenced code blocks are parsed as sections (heuristic parser, no markdown AST).
- Blame regexes are English-only; non-English reports get structural checks only.
- Widely adopted, teams may over-optimize for the linter: reports become formulaic and writers hide blame in synonyms the regexes miss. Treat findings as prompts for review, not proof of blamelessness.

## FAQ

**Does it call any service or model?** No. Pure stdlib, offline, deterministic.

**Can I change required sections?** Yes — pass `--template sections.json` with `{"required_sections": [...]}`.

**When NOT to use this tool?** Don't use it as a gate that blocks an incident review from being published over WARN-level findings — that incentivizes quieter reports. Also skip it if your team uses a hosted incident tool that already enforces structure; two enforcers will drift.

## [Core Assumptions]

1. Teams write postmortems as markdown with `##`-level sections; other formats (Confluence exports, DOCX) are out of scope.
2. "Blameless" is approximable by lexical patterns; systematic-cause vs person-cause framing is largely detectable without NLP.
3. Action items without owners are materially less likely to complete, so an owner marker is worth requiring.
4. Exit-code discipline (0/1/2) is a usable CI integration contract.

---

Confidence: High (≥80%) that structural checks (sections/owners/timestamps) behave as documented — covered by 70 self-test cases. Medium (60-79%) that the blame regex set catches the majority of blame phrasing in English reports — plausible from pattern design but not corpus-validated. Data as of 2026-10-13.

---

Part of the [zhengming-toolbox](https://github.com/chenhz01/zhengming-toolbox) — 105 purpose-built AI-engineering tools across neglected niches.

Related tools: [deprecation-timeline-audit](https://github.com/chenhz01/deprecation-timeline-audit) · [pr-size-scorer](https://github.com/chenhz01/pr-size-scorer) · [release-notes-spec](https://github.com/chenhz01/release-notes-spec)
