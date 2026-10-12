# Changelog

## v0.1.1 (2026-10-13)

Round-2 revision after full self-review of the v0.1.0 draft:

- Added 4 extreme-edge test cases (blame inside timeline entries, duplicated
  template section names, CRLF blame scoring, UTF-8 BOM input through the CLI);
  suite grew 66 -> 70 cases, all PASS.
- Fixed self-test fixtures: CLI cases no longer pass a nonexistent subcommand
  word; partial-report fixtures replaced with complete reports where the
  "no errors" contract was asserted.
- Measured and documented Performance numbers ([Measured] tags, repro commands).
- Added ALIGNMENT.md (rules 85-100 audit, 16 items with evidence).

## v0.1.0 (2026-10-13)

Initial draft:

- Core linter: required-section validation (default: Timeline / Root Cause /
  Action Items / Impact; JSON-template overridable), five blame-language
  regex detectors with line numbers, action-item owner checks, timeline
  timestamp checks, root-cause depth warnings.
- CLI (`check`, `--template`, `--json`, `--strict`, `--max-blame`) with
  exit-code contract 0/1/2.
- Self-test suite: 66 cases across functional / exception / extreme-edge
  classes, `SUMMARY: PASS n/n` reporting, four-defence template (SystemExit
  capture, Unicode-safe regexes, `newline=""` fixtures, SUMMARY last line).
- README, MIT LICENSE.
