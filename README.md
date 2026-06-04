# StudyForge

StudyForge is a **local-first AI study pipeline** that helps you turn course PDFs into reviewed notes, audited study material, and practical study files—without sending your whole library to the cloud by default.

## What it does today

StudyForge can:

- create courses from a folder template
- register source PDFs per course
- extract text from PDFs
- chunk extracted text for LLM-sized packets
- run **LM Studio** local digest (per chunk + combined digest)
- review local digest quality with **rule-based checks** (no AI)
- export and import **intermediate audits** (manual packet or automated Google AI)
- export and import **final audits** (manual packet workflow)
- **generate final study packs** from the latest final audit (deterministic parser, no AI)
- **practice active recall** with self-grading (correct / partial / wrong / skipped, no AI)
- **track mistakes and weak points** from recall practice (manual, deterministic)
- show **Pipeline Doctor** status and next recommended step in the GUI

Outputs live under each course folder (for example `02_Extracted_Text/`, `03_Local_Digests/`, `04_Intermediate_Audits/`, `05_Final_Audits/`, `06_Study_Outputs/`).

## Quick GUI start

From the project root:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Or:

```bash
python scripts/launch_gui.py
```

1. **Courses** — create or select a course.
2. **Sources** — upload a PDF.
3. **Pipeline** — extract, chunk, local digest, review; use **Pipeline Doctor** for the next step; after a final audit, use **Study Pack** to generate guides and flashcards.
4. **Audits** — export/import intermediate and final audits (or run automated intermediate audit if Google API key is set).
5. **Active Recall** — practice questions one at a time after study pack generation; self-grade and log attempts.
6. **Review Tracker** — mistakes log, weak points, and promote weak recall attempts to trackers.
7. **Settings** — LM Studio is configured on Pipeline; Google API key for automated intermediate audit.

The GUI wraps the same backend as the CLI scripts—you do not need to type commands for most steps.

**Study Pack (GUI):** On **Pipeline**, after importing a final audit, use the **Study Pack** section (below Pipeline Doctor). After importing a final audit, generate a study pack to create the final guide, flashcards, formula sheet, quiz, active recall file, and weak-points seed.

## Quick CLI end-to-end workflow

One-time scaffold (safe to re-run):

```bash
python scripts/init_studyforge_structure.py
```

Full path for one source (replace paths and course name as needed):

```bash
python scripts/create_course.py --code ECA1010 --name "Microeconomics"

python scripts/add_source.py --course ECA1010_Microeconomics --type textbook --file "C:\path\to\book.pdf" --title "Main Textbook"

python scripts/extract_source.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/chunk_source.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/check_lm_studio.py --base-url "http://localhost:1234/v1"

python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1

python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/review_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/import_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\to\gemini_audit.md"

python scripts/export_final_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/import_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\to\final_audit.md"

python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Active recall practice (after study pack; no AI grading):

```bash
python scripts/active_recall.py --course ECA1010_Microeconomics --source-id SRC-0001 --list
python scripts/active_recall.py --course ECA1010_Microeconomics --source-id SRC-0001 --summary
python scripts/active_recall.py --course ECA1010_Microeconomics --source-id SRC-0001 --record \
  --question-id AR-SRC-0001-Q001 --answer "My answer" --grade partial --notes "Optional note"

python scripts/active_recall.py --course ECA1010_Microeconomics --source-id SRC-0001 --record \
  --question-id AR-SRC-0001-Q001 --answer "My answer" --grade wrong --create-mistake --create-weak-point
```

Mistakes log and weak points (course-level under `07_My_Work/`):

```bash
python scripts/mistakes.py --course ECA1010_Microeconomics --list
python scripts/mistakes.py --course ECA1010_Microeconomics --export

python scripts/weak_points.py --course ECA1010_Microeconomics --list
python scripts/weak_points.py --course ECA1010_Microeconomics --export
```

Check progress anytime:

```bash
python scripts/pipeline_status.py --course ECA1010_Microeconomics --source-id SRC-0001
```

### Automated intermediate audit (optional)

Requires `GOOGLE_API_KEY` (`.env` or Settings in GUI). Output is **sanitized** before save (see below).

```bash
python scripts/run_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/run_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --keep-raw
```

`--keep-raw` skips sanitizer cleanup for debugging only.

## Privacy note

**Do not commit real course data.** `.gitignore` ignores all folders under `courses/` except `courses/README.md` and `courses/_Course_Template/`. That includes PDFs, extracted text, digests, audits, and `06_Study_Outputs/` study packs.

Also ignored: `.env`, `*.env`, `config/local_secrets.json`, local DB files, and common temp/log paths.

If you previously committed a real course folder, run `git rm -r --cached courses/YourCourse` once (files stay on disk) so Git stops tracking them.

## Audit sanitizer (automated intermediate audit)

`src/studyforge/audits/audit_sanitizer.py` provides `sanitize_audit_output()` / `sanitize_audit_output_with_stats()`. It strips scratchpad blocks, excessive reasoning, and other noise from **automated** Google AI intermediate audit responses before they are saved. Manual imports via `import_intermediate_audit.py` are stored as provided.

Tests: `tests/test_audit_sanitizer.py`, `tests/test_intermediate_audit_jobs.py`.

## Current limitations (MVP)

- No SQLite / central database
- No vector search or RAG index
- No autonomous agents
- No spaced repetition scheduling
- No AI grading of quiz answers
- Study pack generation is **deterministic** (parses final audit Markdown; does not call an LLM)
- Active recall uses **self-grading** only (no AI answer checking)
- Mistakes and weak points are **manual** trackers (JSON + optional Markdown export)
- Final audit quality depends on your external reviewer (ChatGPT, etc.) and template headings
- LM Studio and Google AI require local setup and API keys where applicable

## Recommended first real test

1. Create a course with one short PDF (a few pages).
2. Run through the [MVP manual test checklist](docs/MVP_MANUAL_TEST_CHECKLIST.md).
3. After final audit import, generate the study pack and open `06_Study_Outputs/study_guides/` and `flashcards/`.
4. Confirm Pipeline Doctor shows **Study pack ready**.
5. Run `git status` and confirm no files under your real course path are staged.

## More CLI detail

Individual scripts (flags, overwrite, limits) are listed in [scripts/README.md](scripts/README.md).

## Layout

- `config/` — application settings
- `courses/` — per-course data and pipeline outputs (real courses gitignored)
- `docs/` — specifications, planning, manual test checklist
- `prompts/` — LLM prompt templates
- `scripts/` — setup and utility scripts
- `src/studyforge/` — Python application code
- `app.py` — Streamlit GUI entry point
- `tests/` — automated tests

See each folder's README for details.
