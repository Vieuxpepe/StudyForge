# StudyForge MVP Manual Test Checklist

Use this checklist after code changes or before trusting StudyForge with a real course.
Work through one source end-to-end on your machine.

## Checklist

- [ ] Launch GUI
- [ ] Open **Today** page and confirm summary counts match your course data
- [ ] Optional: open **Course Quality** page or run `course_quality.py --export`; confirm source health table and recommendations
- [ ] Optional: open **Evidence Trace** for a chunked source; inspect source chunk, digest chunk, and audit mentions
- [ ] Create/select course
- [ ] Optional: create course backup (`python scripts/backup_course.py --course YourCourse` or **Courses** → **Course backup**); confirm zip under `08_App_Data/exports/backups/`
- [ ] Optional: verify backup (`python scripts/verify_backup.py --file path\to\backup.zip` or **Courses** → **Backup verification**); preview restore; safe restore to new folder only (`--restore-as`); existing courses are never overwritten in v1
- [ ] Upload/register a real PDF
- [ ] Confirm source appears in dashboard
- [ ] Try **Run next recommended step** on Pipeline (Guided Workflow) for one step
- [ ] Confirm Pipeline Doctor updates after the guided step
- [ ] Extract PDF
- [ ] Confirm extraction quality report exists (`02_Extracted_Text/extraction_logs/SRC-0001_extraction_quality_report.json`) or run **Pipeline** → **Extraction Quality** / `check_extraction_quality.py`
- [ ] If quality is `needs_review` or `failed`, inspect flagged pages before chunking
- [ ] Open extracted text preview
- [ ] Chunk source
- [ ] Confirm chunk manifest exists
- [ ] Check LM Studio connection
- [ ] Run local digest first chunk only
- [ ] Inspect first chunk digest
- [ ] Run full local digest
- [ ] Run local digest review
- [ ] Export intermediate audit packet
- [ ] Run/import intermediate audit
- [ ] Export final audit packet
- [ ] Run/import final audit
- [ ] If study pack diagnose quality is weak, run **Final Audit Normalizer** on **Audits** (or `normalize_final_audit.py`)
- [ ] Optional: export repair packet and re-import a manually fixed final audit
- [ ] Run study pack `--diagnose-only` (or GUI **Diagnose final audit only**)
- [ ] Generate study pack and confirm quality status is not `failed`
- [ ] Open final study guide
- [ ] Open flashcards (Markdown), CSV, and Anki TSV under `06_Study_Outputs/flashcards/`
- [ ] Optionally import Anki TSV into Anki manually (File → Import)
- [ ] Regenerate flashcards from **Pipeline** → **Flashcards** export section if needed
- [ ] Open **Flashcards** page and review at least one card (reveal back, self-grade, save)
- [ ] Confirm review log includes `due_date` under `07_My_Work/flashcard_logs/`
- [ ] Confirm due flashcards appear in review plan (**Flashcards Due**) and study sessions when due
- [ ] Optional: create weak point from hard/forgot flashcard grade
- [ ] Open practice quiz
- [ ] Confirm Pipeline Doctor says study pack ready
- [ ] Open **Active Recall** page and list questions
- [ ] Answer one question and save attempt (self-grade)
- [ ] Export active recall summary
- [ ] Confirm log exists under `07_My_Work/active_recall_logs/`
- [ ] Open **Review Tracker** and view weak recall attempts
- [ ] Create a mistake from a weak attempt (or add manually)
- [ ] Create a weak point from a weak attempt (or add manually)
- [ ] Export mistakes and weak points Markdown
- [ ] Confirm `07_My_Work/mistakes_log.json` and `weak_points.json` exist
- [ ] Generate today's review plan on **Review Tracker**
- [ ] Open `07_My_Work/review_sessions/YYYY-MM-DD_review_plan.md`
- [ ] Start a **Study Session** on the Study Session page (or `study_session.py --start`) — course-wide, **Study unit**, or **Exam target** scope
- [ ] Optional: start a unit session (`study_session.py --start --unit-id UNIT-0001`) or **Start unit study session** on **Study Units**
- [ ] Optional: start an exam session (`study_session.py --start --exam-id EXAM-0001`) or **Start exam study session** on **Exam Prep** / **Study Session** (exam target)
- [ ] Confirm session includes review-priority items and unanswered active recall from study packs (when available); unit sessions include unit-level recall/flashcards first, then sources in that unit; exam sessions include only items from the exam target scope (units, direct sources, sources inside units)
- [ ] Complete at least one session item (recall, unanswered recall, mistake, or weak point)
- [ ] Finish session and export summary under `07_My_Work/study_sessions/`
- [ ] Confirm priorities match your open mistakes / weak points / recall gaps / flashcards / unanswered recall
- [ ] On **Study Units**, export a **Unit Synthesis Packet** (optional: include learning state)
- [ ] Confirm `08_App_Data/reports/study_units/UNIT-XXXX_synthesis_packet.md` contains instructions, source materials, and source IDs (no automatic AI call)
- [ ] Paste unified synthesis into external AI, then **Import Unit Synthesis** (file or paste) on **Study Units**
- [ ] Confirm `06_Study_Outputs/study_units/UNIT-XXXX/UNIT-XXXX_synthesis_v001.md` and registry exist; quality status shown (ok / needs_review / failed)
- [ ] Generate **Unit Study Pack** (`generate_unit_study_pack.py` or GUI) after synthesis import
- [ ] Confirm `UNIT-XXXX_unit_study_guide.md`, flashcards, quiz, active recall, and manifest under `06_Study_Outputs/study_units/UNIT-XXXX/`
- [ ] Optional: run `--diagnose-only` before generate
- [ ] After unit study pack: practice unit recall (`unit_review.py --list-recall` / `--record-recall`) and unit flashcards (`--list-flashcards` / `--record-flashcard`); logs under `07_My_Work/unit_active_recall_logs/` and `07_My_Work/unit_flashcard_logs/` (separate from source-level)
- [ ] Start a unit study session and confirm **Unit active recall** and **Unit flashcard** item types appear; grades save to unit logs
- [ ] Generate unit review plan and confirm **Unit Active Recall**, **Unit Flashcards Due**, and **Unit-Level New Practice** sections
- [ ] On **Today**, active units with a unit pack show unit due flashcard and recall gap counts
- [ ] Generate a **source** mock test (`mock_test.py --source-id SRC-0001 --generate` or GUI **Mock Tests**)
- [ ] Generate a **unit** mock test after unit study pack exists (`--unit-id UNIT-0001 --generate`)
- [ ] Confirm Markdown + JSON under `07_My_Work/mock_tests/` with questions and answer key
- [ ] Self-grade and record attempt (`--record --score N --total M`); optional `--weak-topic` creates weak points
- [ ] Optional: grade question-by-question (`grade_mock_test.py --list`, `--grade-question`, `--summary`, `--finalize`, `--export-review`) or **Mock Tests → Detailed Grading**
- [ ] Confirm partial credit works (correct=1, partial=0.5) and finalizing records a normal mock attempt with detailed score in notes
- [ ] Confirm graded data under `07_My_Work/mock_tests/graded/` and review Markdown exports
- [ ] Confirm `mock_test_attempts.json` and **Today** shows latest mock test score when recorded
- [ ] If a mock test has ungraded questions, **Today** may recommend finishing grading
- [ ] Create an **exam target** (`exam_targets.py --create` or GUI **Exam Prep**) with units, sources, date, and target score
- [ ] Confirm `00_Master/exam_targets.json` stores the target
- [ ] Run `exam_prep.py --exam-id EXAM-0001 --export` (or GUI **Generate exam prep plan**)
- [ ] Confirm plan includes scope, readiness, review counts, mock status, recommended actions, and checklists under `07_My_Work/exam_prep/`
- [ ] View **Exam Readiness** on **Exam Prep** (or `exam_readiness.py --exam-id EXAM-0001`) — score, status, breakdown, blockers, recommendations
- [ ] Optional: export readiness report (`exam_readiness.py --export`) to `07_My_Work/exam_prep/EXAM-0001_exam_readiness_report.md` and `.json`
- [ ] On **Today**, confirm nearest exam shows readiness when an active exam target exists
- [ ] Readiness score is deterministic guidance only — not a guarantee of exam performance
- [ ] On **Today**, confirm nearest exam and active exam target count when targets exist

## Pass criteria

- No crashes
- Pipeline Doctor next action makes sense at each step
- Generated files exist on disk under the course folder
- Study pack files are usable (guide, flashcards Markdown/CSV/Anki TSV, quiz, active recall, weak-points seed)
- No private PDFs or course outputs committed to Git (`git status` should not list files under `courses/<YourCourse>/` except the template)

## GUI quick map

Sidebar **Go to** uses grouped labels (e.g. `Build Study Material · Pipeline`, `Study / Review · Study Session`). Select a **Course** in the sidebar first when a page needs one.

| Section | Step | Where in GUI |
|---------|------|----------------|
| Today | What to study today; navigation helper | **Today** (expand **Where should I go?**) |
| Build Study Material | Pipeline overview | **Dashboard** |
| Build Study Material | Source PDF | **Sources** |
| Build Study Material | Guided next step | **Pipeline** → **Guided Workflow** |
| Build Study Material | Extract / chunk / digest / review | **Pipeline** (manual controls) |
| Build Study Material | Extraction quality check | **Pipeline** → **Extraction Quality** |
| Build Study Material | Pipeline Doctor + study pack | **Pipeline** (top: Doctor; **Study Pack** after final audit) |
| Build Study Material | Intermediate/final audits, normalizer | **Audits** |
| Build Study Material | Group sources into topic/exam units | **Study Units** |
| Build Study Material | Unit readiness + review summary | **Study Units** → **Unit Dashboard** |
| Build Study Material | Unit-specific review plan | **Study Units** → **Generate unit review plan** |
| Build Study Material | Unit synthesis packet (manual AI) | **Study Units** → **Export synthesis packet** |
| Build Study Material | Import versioned unit synthesis | **Study Units** → **Import Unit Synthesis** |
| Build Study Material | Unit study pack from synthesis | **Study Units** → **Unit Study Pack** |
| Study / Review | Guided study session | **Study Session** |
| Study / Review | Active recall practice | **Active Recall** |
| Study / Review | Flashcard review | **Flashcards** |
| Study / Review | Mock test generation and scoring | **Mock Tests** |
| Study / Review | Exam targets and prep plans | **Exam Prep** |
| Study / Review | Mistakes / weak points / review plan | **Review Tracker** |
| Quality / Trust | Course trust/readiness across sources | **Course Quality** |
| Quality / Trust | Evidence chain inspection | **Evidence Trace** |
| Course Tools | Course create/select | **Courses** |
| Course Tools | Course backup | **Courses** → **Course backup** |
| Course Tools | Backup verify / safe restore | **Courses** → **Backup verification** |
| Settings | LM Studio URL / model / chunking / digest / GUI defaults | **Settings** → saves `config/local_app_settings.json` (gitignored; no API keys) |
| Settings | LM Studio overrides per session | **Pipeline** (uses saved defaults on startup) |
| Settings | Google API key | **Settings** (`.env` or `config/local_secrets.json`; not app settings) |

**Smoke:** Open the GUI, confirm each sidebar group appears in **Go to**, switch pages, and verify each page shows a one-line caption under the title.

**Settings smoke:** On **Settings**, set LM Studio base URL (e.g. LAN IP), click **Save settings**, restart GUI — **Pipeline** should show the saved URL. Confirm `config/local_app_settings.json` is not tracked by Git.

## CLI equivalent (optional)

See `README.md` — **Quick CLI end-to-end workflow** for the full command sequence.

Final audit normalizer (if headings do not match template):

```bash
python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/normalize_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --import-as-new-version --overwrite
```

Study pack (after final audit import):

```bash
python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001
```

## Automated intermediate audit note

Automated intermediate audits (`run_intermediate_audit.py`) pass through `audit_sanitizer.py` to remove scratchpad/reasoning noise before save. Use `--keep-raw` only when debugging. Manual imports are not sanitized automatically.

## Notes / Issues Found

<!-- Record anything that failed, looked wrong, or needs a follow-up -->
