# StudyForge

StudyForge is a **local-first AI study pipeline** that helps you turn course PDFs into reviewed notes, audited study material, and practical study files—without sending your whole library to the cloud by default.

## What it does today

StudyForge can:

- create courses from a folder template
- register source PDFs per course
- extract text from PDFs
- check extraction quality after PDF extraction (empty/low-text pages, suspicious artifacts — no OCR, no AI)
- chunk extracted text for LLM-sized packets
- run **LM Studio** local digest (per chunk + combined digest)
- review local digest quality with **rule-based checks** (no AI)
- export and import **intermediate audits** (manual packet or automated Google AI)
- export and import **final audits** (manual packet workflow)
- **generate final study packs** from the latest final audit (deterministic parser, no AI)
- **practice active recall** with self-grading (correct / partial / wrong / skipped, no AI)
- **track mistakes and weak points** from recall practice (manual, deterministic)
- **generate daily review plans** from open mistakes, weak points, and weak recall attempts
- **course quality report** — trust/readiness summary across all sources (deterministic, no AI)
- **evidence trace viewer** — inspect source chunk → digest → audit chain (deterministic, no semantic search)
- show **Pipeline Doctor** status and next recommended step in the GUI (including stale study pack warnings when a newer final audit was imported)
- **guided workflow** — run one recommended pipeline step per click (not autonomous)

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

The sidebar **Go to** menu groups pages into six sections:

| Section | Pages |
|---------|--------|
| **Today** | Today — what to review right now |
| **Build Study Material** | Dashboard, Sources, Pipeline, Audits, Study Units |
| **Study / Review** | Study Session, Active Recall, Flashcards, Mock Tests, Exam Prep, Review Tracker |
| **Quality / Trust** | Course Quality, Evidence Trace |
| **Course Tools** | Courses (create course, backup, verify, restore) |
| **Settings** | Local app preferences and Google API key |

Each page opens with a short caption describing its role. **Today** includes a **Where should I go?** helper for common tasks.

1. **Today** — dashboard of what to study now: due flashcards, active recall gaps, open mistakes/weak points, review plan status, and recommended next action (deterministic; no calendar integration).
2. **Dashboard** — source pipeline overview for the selected course.
3. **Sources** — upload a PDF.
4. **Pipeline** — **Guided Workflow** runs one Pipeline Doctor step per click; **Pipeline Doctor** shows progress; manual controls remain below; after a final audit, use **Study Pack**.
5. **Audits** — export/import intermediate and final audits; **Final Audit Normalizer** maps messy headings to the study-pack template (or export a manual repair packet).
6. **Study Units** — group multiple sources into a named topic/chapter/exam target; **Unit Dashboard** aggregates readiness, review items, and output paths per unit; unit review plans include unit-level active recall and flashcards plus source-filtered items; **Unit Synthesis Packet** exports multi-source material for manual paste into ChatGPT/Gemini; **Unit Synthesis Import** stores versioned unified guides; **Unit Study Pack** generates unit-level guides, flashcards, quiz, and active recall from the latest synthesis (deterministic parser only).
7. **Study Session** — guided session through today's priorities (recall gaps, mistakes, weak points, flashcards) plus unanswered active recall questions from study packs; course-wide, focused on one **Study Unit**, or focused on an **Exam target** (units, direct sources, and sources inside included units — deterministic filtering, no AI); self-graded only.
8. **Active Recall** — practice questions one at a time after study pack generation; self-grade and log attempts.
9. **Flashcards** — review exported flashcards in-app, self-grade (easy/good/hard/forgot/skipped), and log results with lightweight due scheduling (+1 to +7 days by grade); due cards appear in review plans and study sessions; optional weak point creation; not full Anki/SM-2.
10. **Mock Tests** — generate deterministic practice tests from source or unit study packs (practice quiz, active recall, flashcards); grade question-by-question with partial credit, finalize into a normal mock attempt, export a post-mock review report, or use quick total-score entry; missed questions can create mistakes/weak points; no AI grading.
11. **Exam Prep** — define exam targets (date, units, sources, target score), view a deterministic **exam readiness score** (material readiness, review load, mock test performance, time pressure — guidance only, not a grade guarantee), and generate prep plans from readiness, review items, and mock test history; no calendar integration or AI planning.
12. **Review Tracker** — mistakes log, weak points, review session planner, and promote weak recall attempts to trackers.
13. **Course Quality** — trust/readiness report across sources.
14. **Evidence Trace** — inspect chunks, digests, and audits side by side.
15. **Courses** — create or select a course; backup, verify, and safe restore.
16. **Settings** — save local app preferences (LM Studio URL/model, chunking, digest, GUI defaults) to gitignored `config/local_app_settings.json`; **do not** store API keys there. Google API key for automated intermediate audit stays in `.env` or `config/local_secrets.json`.

Saved LM Studio LAN URL and model are applied as Pipeline defaults on startup. CLI scripts keep their own built-in defaults unless you pass flags.

The GUI wraps the same backend as the CLI scripts—you do not need to type commands for most steps.

**Study Pack (GUI):** On **Pipeline**, after importing a final audit, use the **Study Pack** section (below Pipeline Doctor). After importing a final audit, generate a study pack to create the final guide, flashcards (Markdown, CSV, and Anki TSV), formula sheet, quiz, active recall file, and weak-points seed. Flashcards are deterministic exports from final audit sections—import the Anki TSV manually into Anki. No spaced repetition scheduling is built in yet.

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

python scripts/check_extraction_quality.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/chunk_source.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/check_lm_studio.py --base-url "http://localhost:1234/v1"

python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1

python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/review_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/import_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\to\gemini_audit.md"

python scripts/export_final_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001

python scripts/import_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\to\final_audit.md"

python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --import-as-new-version --overwrite
python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --export-repair-packet --overwrite

python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001 --diagnose-only
```

Study pack generation is **deterministic** (no AI) and usually finishes in seconds. That is normal. After generation, check the **quality** report in the CLI or GUI — if the final audit does not use the expected `##` headings, many sections may be empty placeholders (`Not found in final audit.`). Use `--diagnose-only` before overwriting an existing pack to preview section coverage. If quality is `needs_review` or `failed`, run **Final Audit Normalizer** (`scripts/normalize_final_audit.py` or **Audits** page) to map headings to the template, or export a **repair packet** for manual ChatGPT cleanup (no AI inside StudyForge). If you import a newer final audit after generating a study pack, Pipeline Doctor warns that the pack may be stale and suggests **Regenerate study pack** (use overwrite).

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

Review session plan (deterministic daily priorities from mistakes, weak points, and active recall):

```bash
python scripts/review_plan.py --course ECA1010_Microeconomics
python scripts/review_plan.py --course ECA1010_Microeconomics --limit 5 --overwrite
python scripts/review_plan.py --course ECA1010_Microeconomics --date 2026-06-04

python scripts/study_session.py --course ECA1010_Microeconomics --start --limit 10
python scripts/study_session.py --course ECA1010_Microeconomics --start --unit-id UNIT-0001 --limit 10
python scripts/study_session.py --course ECA1010_Microeconomics --latest
python scripts/study_session.py --course ECA1010_Microeconomics --session-id SESSION-20260604-120000 --complete-item SESSION-ITEM-0001 --result partial --notes "Still confused"
python scripts/study_session.py --course ECA1010_Microeconomics --session-id SESSION-20260604-120000 --finish
python scripts/study_session.py --course ECA1010_Microeconomics --session-id SESSION-20260604-120000 --export
```

Unit synthesis packet (manual export for ChatGPT/Gemini; no API call):

```bash
python scripts/unit_synthesis_packet.py --course ECA1010_Microeconomics --unit-id UNIT-0001
python scripts/unit_synthesis_packet.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --overwrite
python scripts/unit_synthesis_packet.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --no-learning-state
```

Import unit synthesis after manual AI synthesis (versioned; never overwrites older versions):

```bash
python scripts/import_unit_synthesis.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --file "C:\path\to\unit_synthesis.md"
python scripts/import_unit_synthesis.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --text "# Unit Synthesis\n..." --synthesizer-name ChatGPT --notes "First import"
```

Unit study pack (from latest imported synthesis; no AI):

```bash
python scripts/generate_unit_study_pack.py --course ECA1010_Microeconomics --unit-id UNIT-0001
python scripts/generate_unit_study_pack.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --diagnose-only
python scripts/generate_unit_study_pack.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --overwrite
```

Unit-level review (separate logs from source-level; simple due dates for unit flashcards, not full spaced repetition):

```bash
python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --list-recall
python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --record-recall --question-id UAR-UNIT-0001-Q001 --answer "..." --grade partial
python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --list-flashcards
python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --record-flashcard --card-id UFC-UNIT-0001-0001 --grade hard
python scripts/unit_review.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --summary
```

Unit study packs feed unit-focused study sessions, unit review plans, and Today Dashboard unit counts. Logs: `07_My_Work/unit_active_recall_logs/`, `07_My_Work/unit_flashcard_logs/`.

Mock tests (deterministic; self-grade only):

```bash
python scripts/mock_test.py --course ECA1010_Microeconomics --source-id SRC-0001 --generate
python scripts/mock_test.py --course ECA1010_Microeconomics --unit-id UNIT-0001 --generate --questions 15
python scripts/mock_test.py --course ECA1010_Microeconomics --record --mock-test-id MT-SRC-0001-2026-06-04-120000 --scope source --source-id SRC-0001 --score 14 --total 20 --notes "Missed formulas" --weak-topic "CPI formula"
python scripts/mock_test.py --course ECA1010_Microeconomics --summary
```

Outputs: `07_My_Work/mock_tests/`; attempt log: `mock_test_attempts.json`.

Exam targets and prep plans (deterministic; no calendar sync):

```bash
python scripts/exam_targets.py --course ECA1010_Microeconomics --list
python scripts/exam_targets.py --course ECA1010_Microeconomics --create --title "Quiz 2" --date 2026-06-20 --target-score 80 --units UNIT-0001 UNIT-0002 --sources SRC-0005
python scripts/exam_targets.py --course ECA1010_Microeconomics --summary EXAM-0001
python scripts/exam_prep.py --course ECA1010_Microeconomics --exam-id EXAM-0001 --export --overwrite
```

Data: `00_Master/exam_targets.json`; plans: `07_My_Work/exam_prep/`.

Guided Workflow (one step per click; uses Pipeline Doctor `next_action`):

```bash
python scripts/run_next_step.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/run_next_step.py --course ECA1010_Microeconomics --source-id SRC-0001 --full-digest
python scripts/run_next_step.py --course ECA1010_Microeconomics --source-id SRC-0001 \
  --base-url "http://192.168.2.152:1234/v1" --model "google/gemma-4-e4b"
```

The **Run next recommended step** button in the GUI runs exactly one step. It does not loop through the full pipeline and does not call Google AI for intermediate audits automatically (export packet only).

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

`source_registry.json` and audit registries store **absolute local paths** to files on your machine. That is intentional for local-only use; do not commit those JSON files (they stay under gitignored `courses/`).

If you previously committed a real course folder, run `git rm -r --cached courses/YourCourse` once (files stay on disk) so Git stops tracking them.

**Back up real course data locally:** course folders are gitignored, so use `python scripts/backup_course.py --course YourCourse` to create a zip under `courses/YourCourse/08_App_Data/exports/backups/`. Verify backups with `python scripts/verify_backup.py --file path\to\backup.zip`. Safe restore to a **new** course folder only (`--restore-as`); existing course folders are never overwritten in v1. Backups may contain private PDFs, extracted text, audits, and study logs — store them safely.

## Audit sanitizer (automated intermediate audit)

`src/studyforge/audits/audit_sanitizer.py` provides `sanitize_audit_output()` / `sanitize_audit_output_with_stats()`. It strips scratchpad blocks, excessive reasoning, and other noise from **automated** Google AI intermediate audit responses before they are saved. Manual imports via `import_intermediate_audit.py` are stored as provided.

Tests: `tests/test_audit_sanitizer.py`, `tests/test_intermediate_audit_jobs.py`.

## Architecture / regression notes

See [docs/REGRESSION_LOGIC_AUDIT.md](docs/REGRESSION_LOGIC_AUDIT.md) for status-flow rules, parser overlap notes, CLI/GUI alignment, and known risks from the stabilization audit.

## Current limitations (MVP)

- No SQLite / central database
- No vector search or RAG index
- No autonomous agents
- No spaced repetition scheduling
- No AI grading of quiz answers
- Study pack generation is **deterministic** (parses final audit Markdown; does not call an LLM). Quality diagnostics (`ok` / `needs_review` / `failed`) check whether headings were found.
- Active recall uses **self-grading** only (no AI answer checking)
- Mistakes and weak points are **manual** trackers (JSON + optional Markdown export)
- Final audit quality depends on your external reviewer (ChatGPT, etc.) and template headings
- LM Studio and Google AI require local setup and API keys where applicable

## Recommended first real test

1. Create a course with one short PDF (a few pages).
2. Run through the [MVP manual test checklist](docs/MVP_MANUAL_TEST_CHECKLIST.md).
3. After final audit import, generate the study pack and open `06_Study_Outputs/study_guides/` and `flashcards/` (Markdown, CSV, and `_anki.tsv` for Anki import).
4. Confirm Pipeline Doctor shows **Study pack ready**.
5. Run `git status` and confirm no files under your real course path are staged.

## More CLI detail

Individual scripts (flags, overwrite, limits) are listed in [scripts/README.md](scripts/README.md).

## Tests

Local:

```bash
python -m unittest discover -s tests -q
```

GitHub Actions:

Tests run automatically on push and pull requests (workflow: **StudyForge Tests** in `.github/workflows/tests.yml`). CI uses Python 3.11, installs `requirements.txt`, and runs the same unittest command. No LM Studio or API keys are required — tests use temporary directories and mocks.

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
