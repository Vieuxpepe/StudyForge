# Codex Audit Report

## Date

2026-06-05

## Test Result

- Baseline run: `python -m unittest discover -s tests -q`
- Final run: `python -m unittest discover -s tests -q`
- Result: 526 tests passed, 0 failed

## Git / Privacy Check

- `git ls-files courses` only includes `courses/README.md` and `courses/_Course_Template/**`
- Real course folders observed as ignored: `courses/ECA1010_Microeconomics/`, `courses/QA1000_Smoke_Test/`
- No tracked private course data found
- Working tree at the end of the audit is not fully clean because this report file was added and the repo already contained in-progress work during the audit

## Executive Summary

The core privacy boundary is holding: no real course folders are tracked, ignored course folders are ignored correctly, and the full unittest suite passes.

The highest-value issues were in two study-behavior paths:

1. Detailed mock-test finalization could collapse partial credit into a rounded whole-attempt score, which could distort mock history and exam readiness.
2. Unit dashboards did not warn when a unit study pack was generated from an older synthesis than the latest imported synthesis.

Both were fixed with focused tests.

## Critical Findings

None.

## Important Findings

### 1. Important
- Files: `src/studyforge/study/mock_test_grading.py:283`, `src/studyforge/study/mock_tests.py:567`
- Issue: `finalize_mock_test_grading()` converted detailed grading into a normal mock attempt by rounding `score_correct_equivalent` before recording it.
- Why it matters: a graded result like `1.5/2` could be recorded as `2/2` or `0/1` depending on rounding, which can misstate mock history and feed misleading percentages into exam prep/readiness.
- Suggested fix: preserve fractional `score_correct` values when converting detailed grading into a recorded mock attempt.
- Whether fixed: yes
- Test added if fixed: `tests/test_mock_test_grading.py:288`

### 2. Important
- Files: `src/studyforge/study/study_unit_dashboard.py:405`, `src/studyforge/study/study_unit_dashboard.py:424`
- Issue: unit dashboard data exposed the latest synthesis and latest unit pack separately, but did not compare the manifest’s `based_on_unit_synthesis_id` against the latest imported synthesis.
- Why it matters: a user could import `US-UNIT-XXXX-V003` while still studying from a pack built from `V002` with no stale warning, which is the unit-level counterpart of the source-level stale study-pack risk already handled in `pipeline_status.py`.
- Suggested fix: compare the current manifest’s synthesis ID to `latest_synthesis_id`, surface a warning, and recommend regenerating the unit study pack.
- Whether fixed: yes
- Test added if fixed: `tests/test_study_unit_dashboard.py:294`

## Minor Findings

### 3. Minor
- Files: `scripts/mock_test.py:52`, `src/studyforge/study/mock_tests.py:478`
- Issue: the CLI advertises `--overwrite`, but generation treats it as a reserved no-op because mock tests always emit new timestamped files.
- Why it matters: the flag suggests behavior that does not exist, which can confuse users and docs readers during recovery/debugging workflows.
- Suggested fix: either remove the flag from the CLI/docs or implement explicit semantics such as “replace latest generated pair for same scope.”
- Whether fixed: yes (removed misleading `--overwrite` from `scripts/mock_test.py`; generation always uses timestamped files)
- Test added if fixed: no

### 4. Minor
- Files: `scripts/app_settings.py:58`, `scripts/check_lm_studio.py:44`
- Issue: the quiet unittest run is noisy because CLI smoke tests print local temp paths and sample LM Studio URLs to stdout.
- Why it matters: this is not a repo secret leak, but it makes regression runs harder to scan and can expose local path/host details in copied logs.
- Suggested fix: capture stdout in CLI smoke tests or add a quiet mode for those scripts when exercised from tests.
- Whether fixed: no
- Test added if fixed: no

## Fixes Applied

- Preserved partial-credit percentages when finalizing detailed mock grading into recorded mock attempts.
- Added unit-dashboard stale-pack detection based on `based_on_unit_synthesis_id` vs. `latest_synthesis_id`.

## Tests Added

- `tests/test_mock_test_grading.py:288` — verifies finalized detailed grading keeps `1.5/2` as `75.0%`
- `tests/test_study_unit_dashboard.py:294` — verifies stale unit study packs are flagged after a newer synthesis import

## Remaining Risks

- `scripts/mock_test.py --overwrite` was removed because timestamped generation does not need it.
- The unittest suite still emits noisy CLI output even under `-q`.
- The repository contained active in-progress work during the audit, so future merges should re-run the full suite after that work settles.

## Recommended Next Actions

1. ~~Remove or implement `mock_test.py --overwrite`~~ — removed from CLI (timestamped files only).
2. Silence CLI smoke-test stdout in unit tests to make regressions easier to spot.
3. Re-run the full suite after any additional mock-test, unit-dashboard, or study-session changes because those areas now share more scope-sensitive logic.

## Files Changed

- `docs/CODEX_AUDIT_REPORT.md`
- `src/studyforge/study/mock_tests.py`
- `src/studyforge/study/mock_test_grading.py`
- `src/studyforge/study/study_unit_dashboard.py`
- `tests/test_mock_test_grading.py`
- `tests/test_study_unit_dashboard.py`
