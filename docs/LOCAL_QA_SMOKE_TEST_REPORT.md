# Local QA Smoke Test Report

## Date

2026-06-04 (local run on developer machine)

## Environment

| Item | Value |
|------|--------|
| Python | 3.10.9 |
| OS | Windows 10 (build 26200) |
| Project path | `C:\StudyForge` |
| LM Studio (localhost) | `http://localhost:1234/v1` — OK, 9 models |
| LM Studio (LAN) | `http://192.168.2.152:1234/v1` — OK, 9 models |
| Model used (digest) | `google/gemma-4-e4b` |
| Digest scope | 1 chunk only (`--limit-chunks 1`) |
| Disposable course | `QA1000_Smoke_Test` (folder `courses/QA1000_Smoke_Test/`) |
| Real course touched | `ECA1010_Microeconomics` — **not modified** during QA (only read via git status) |

---

## Summary

| Area | Result | Notes |
|------|--------|-------|
| Unit tests (230) | **Pass** | `python -m unittest discover -s tests -q` |
| Git / privacy | **Warning** | `.gitignore` works for new QA course; **ECA1010 real data still tracked in Git** |
| Disposable course setup | **Pass** | Created QA1000, 3-page PDF, SRC-0001 |
| Extract / chunk | **Pass** | 3 pages, 69 words, 1 chunk |
| Pipeline Doctor (mid-pipeline) | **Pass** | Recommended `run_local_digest` after chunking |
| Intermediate packet (pre-digest) | **Fail** (expected) | Requires local digest first |
| LM Studio connection | **Pass** | localhost + LAN |
| Local digest (1 chunk) | **Pass** | ~69s; combined digest written |
| Digest review | **Pass** | Overall `ok` |
| Intermediate packet export | **Pass** | After digest |
| Fake audit imports | **Pass** | IA + FA imported |
| Study pack diagnose | **Pass** | Quality `ok` (thin-section warnings only) |
| Study pack generate | **Pass** | All 6 output types + manifest |
| Active recall | **Pass** | 2 questions; attempt + summary (after retry) |
| Mistakes / weak points | **Pass** | Created from partial attempt |
| Review plan | **Pass** | Markdown + JSON under `07_My_Work/review_sessions/` |
| Pipeline Doctor (complete) | **Pass** | `study_pack_ready`, sensible warnings |
| Guided workflow | **Pass** | At end: `study_pack_ready`, not auto-runnable; no API step |
| Streamlit GUI | **Pass** | Server started on port 8505 without crash |
| Normalizer CLI on QA course | **Not run** | Out of smoke scope; covered by unit tests |

---

## Commands Run

```text
python -m unittest discover -s tests -q
git status
git status --ignored
git ls-files courses

python scripts/create_course.py --code QA1000 --name "Smoke Test"
# Generated PDF: tmp/qa_smoke_test.pdf (PyMuPDF, 3 pages)
python scripts/add_source.py --course QA1000_Smoke_Test --type textbook --file "C:\StudyForge\tmp\qa_smoke_test.pdf" --title "Smoke Test PDF"

python scripts/extract_source.py --course QA1000_Smoke_Test --source-id SRC-0001
python scripts/chunk_source.py --course QA1000_Smoke_Test --source-id SRC-0001
python scripts/pipeline_status.py --course QA1000_Smoke_Test --source-id SRC-0001
python scripts/export_intermediate_audit_packet.py --course QA1000_Smoke_Test --source-id SRC-0001  # failed before digest

python scripts/check_lm_studio.py
python scripts/check_lm_studio.py --base-url "http://192.168.2.152:1234/v1"
python scripts/run_local_digest.py --course QA1000_Smoke_Test --source-id SRC-0001 --base-url "http://192.168.2.152:1234/v1" --model "google/gemma-4-e4b" --limit-chunks 1
python scripts/review_local_digest.py --course QA1000_Smoke_Test --source-id SRC-0001
python scripts/export_intermediate_audit_packet.py --course QA1000_Smoke_Test --source-id SRC-0001

python scripts/import_intermediate_audit.py --course QA1000_Smoke_Test --source-id SRC-0001 --file "C:\StudyForge\tmp\qa_fake_intermediate_audit.md" --notes "QA smoke test"
python scripts/export_final_audit_packet.py --course QA1000_Smoke_Test --source-id SRC-0001
python scripts/import_final_audit.py --course QA1000_Smoke_Test --source-id SRC-0001 --file "C:\StudyForge\tmp\qa_fake_final_audit.md" --notes "QA smoke test final audit"

python scripts/generate_study_pack.py --course QA1000_Smoke_Test --source-id SRC-0001 --diagnose-only
python scripts/generate_study_pack.py --course QA1000_Smoke_Test --source-id SRC-0001

python scripts/active_recall.py --course QA1000_Smoke_Test --source-id SRC-0001 --list
python scripts/active_recall.py --course QA1000_Smoke_Test --source-id SRC-0001 --record --question-id AR-SRC-0001-Q001 --answer "..." --grade partial --create-mistake --create-weak-point --weak-point-concept "CPI definition"
python scripts/active_recall.py --course QA1000_Smoke_Test --source-id SRC-0001 --summary
python scripts/mistakes.py --course QA1000_Smoke_Test --list
python scripts/weak_points.py --course QA1000_Smoke_Test --list
python scripts/review_plan.py --course QA1000_Smoke_Test --overwrite
python scripts/pipeline_status.py --course QA1000_Smoke_Test --source-id SRC-0001

python scripts/run_next_step.py --course QA1000_Smoke_Test --source-id SRC-0001

python -m streamlit run app.py --server.headless true --server.port 8505
```

---

## Results

### Baseline tests

- **230 tests, OK** (includes regression/stale-study-pack tests).
- No commits made during QA.

### Git / privacy check

**Dirty / untracked (code & docs, safe):**

- Modified: README, pipeline_status, study_pack, final_import, streamlit, tests, etc.
- Untracked: `final_audit_normalizer.py`, `normalize_final_audit.py`, regression docs/tests.

**Ignored correctly (examples):**

- `courses/QA1000_Smoke_Test/**` — `git check-ignore` confirms `courses/*` rule.
- Newer ECA1010 artifacts (e.g. `SRC-0001_final_audit_v003.md`, normalization sidecars) show as ignored.

**Important risk — real course data still in Git index:**

- `git ls-files courses` lists **many tracked files under `courses/ECA1010_Microeconomics/`**, including:
  - PDF (`tmpwgbb_y1k.pdf`)
  - Full extracted text and all 10 chunks
  - All chunk digests + combined digest + review files
  - Intermediate/final audit packets and versions (v001–v003 paths in tree)
  - Study outputs paths referenced in registry
  - `source_registry.json` (modified, tracked)
- `.gitignore` `courses/*` does **not** remove files already committed.
- **Recommendation:** `git rm -r --cached courses/ECA1010_Microeconomics` (once), then rely on ignore rules. Do not push course data to a public remote.

### Disposable course — extraction / chunking

| Step | Result |
|------|--------|
| Extract | 3 pages, 69 words → `02_Extracted_Text/extracted_sources/SRC-0001_extracted_text.md` |
| Chunk | 1 chunk → `02_Extracted_Text/chunks/SRC-0001/` |
| Pipeline (after chunk) | Next: `run_local_digest` — **correct** |
| Export IA packet (before digest) | Error: digest required — **correct guard** |

### LM Studio digest

| Check | Result |
|-------|--------|
| localhost:1234 | OK, `google/gemma-4-e4b` available |
| 192.168.2.152:1234 | OK, same models |
| 1-chunk digest | Completed; combined digest at `03_Local_Digests/SRC-0001/SRC-0001_combined_local_digest.md` |
| Digest sections | Required `##` sections present; some leading “Analyze the Request” scratchpad noise (known LLM behavior; review still `ok`) |
| Rule-based review | Overall **ok**, 1 digest OK |

### Audit import / export

| Step | Result |
|------|--------|
| Import fake intermediate | `IA-SRC-0001-V001` |
| Export final packet | `05_Final_Audits/SRC-0001/SRC-0001_final_audit_packet.md` |
| Import fake final | `FA-SRC-0001-V001` |

### Study pack

| Check | Result |
|-------|--------|
| Diagnose quality | **ok** (202 words extracted) |
| Thin sections | corrections, missing_concepts, remaining_uncertainties (expected for minimal fake audit) |
| Generated files | study guide, flashcards, formula sheet, quiz, active recall, weak-points seed, manifest |
| Manifest | `based_on_final_audit_id`: `FA-SRC-0001-V001` |

### Active recall / tracking / review

| Check | Result |
|-------|--------|
| Questions parsed | 2 (`AR-SRC-0001-Q001`, `AR-SRC-0001-Q002`) |
| First `--list` right after generate | **Failed** once (“Active recall file not found”); **succeeded on immediate retry** — minor flake or path timing; file was on disk |
| Record attempt | `AR-ATTEMPT-0001`, partial |
| Mistake | `MISTAKE-0001` |
| Weak point | `WEAK-0001` |
| Review plan | `07_My_Work/review_sessions/2026-06-04_review_plan.md` |
| Pipeline warnings | Open mistakes, weak points, review plan hint — **appropriate** |

### Guided workflow

- At pipeline complete: next action **`study_pack_ready`**.
- `run_next_step.py` exit code 1 with message that step cannot run automatically — **correct** (not a multi-step bot; no Google API call).

### Streamlit GUI

- `python -m streamlit run app.py --server.headless true --server.port 8505` started successfully.
- Local URL: `http://localhost:8505`
- No import traceback on startup.
- Server stopped after check (process terminated).
- Full manual click-through of every page not performed; startup smoke only.

---

## Issues Found

### Important

| ID | Severity | What happened | Expected | Suggested fix | Fixed in QA? |
|----|----------|---------------|----------|---------------|--------------|
| PRIV-01 | **Important** | `git ls-files` shows extensive `ECA1010_Microeconomics` course content tracked | Only template + `courses/README.md` in repo | `git rm -r --cached courses/ECA1010_Microeconomics`; verify `git status` clean for course paths | No (user must approve) |
| UX-01 | Minor→Important | Intermediate packet export before digest fails with error | Clear message | Already clear; document in README/checklist “digest before export” | N/A (by design) |

### Minor

| ID | Severity | What happened | Expected | Suggested fix | Fixed in QA? |
|----|----------|---------------|----------|---------------|--------------|
| AR-01 | Minor | First `active_recall.py --list` failed right after study pack generate | List should work | Investigate race/registry refresh; retry worked | No |
| LLM-01 | Minor | Chunk digest includes scratchpad preamble before `# Local Digest` | Cleaner digest body | Rely on sanitizer/review; optional post-process trim for local digest | No |
| GIT-01 | Minor | `source_registry.json` under ECA1010 modified in working tree | Local-only | Do not commit; untrack course folder | No |

### No action needed

- Study pack quality `ok` on well-formed fake final audit.
- Stale study pack detection not exercised on QA course (single FA version); covered by unit tests.
- Guided workflow does not auto-run paid/API steps.

---

## Recommended Next Actions

1. **Privacy (high):** Remove tracked real course files from Git index (`git rm -r --cached courses/ECA1010_Microeconomics`) without deleting local disk copies.
2. **Commit code/docs only:** Stage application changes + `docs/REGRESSION_LOGIC_AUDIT.md` + this report; never stage `courses/ECA1010_*` or QA outputs unless intentional.
3. **Re-run AR-01** if `active_recall --list` failure reproduces; add regression test if real bug.
4. **Manual GUI pass:** Click through Pipeline (Guided Workflow, Study Pack, quality banners), Audits (normalizer), Active Recall, Review Tracker once per release.
5. **Optional:** Run `normalize_final_audit.py` on ECA1010 with `--audit-version 1` only on disposable copy or after backup — not required for smoke pass.

---

## Notes

- **`QA1000_Smoke_Test` remains on disk** under `courses/QA1000_Smoke_Test/`. It is **ignored by Git** (`courses/*`). Safe to delete locally when finished testing.
- **`tmp/qa_smoke_test.pdf`** and fake audits under `tmp/` are local temp files; not part of the course template.
- **Real course `ECA1010_Microeconomics` was not overwritten** during this QA run.
- **No git commit, no push, no API keys printed.**

---

## Files created during QA (local only)

| Path | Purpose |
|------|---------|
| `courses/QA1000_Smoke_Test/**` | Full disposable pipeline outputs |
| `tmp/qa_smoke_test.pdf` | Source PDF |
| `tmp/qa_fake_intermediate_audit.md` | Fake IA import |
| `tmp/qa_fake_final_audit.md` | Fake FA import |
| `docs/LOCAL_QA_SMOKE_TEST_REPORT.md` | This report |

No application source code was changed during this QA pass.
