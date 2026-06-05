# scripts

Utility and setup scripts.

- `launch_gui.py` — start Streamlit GUI (`app.py`)
- `app_settings.py` — show/reset local app preferences (`--show`, `--reset`, optional `--set-lm-url`, `--set-model`); writes gitignored `config/local_app_settings.json` (no API keys)
- `study_units.py` — group sources into topic bundles (`--list`, `--create`, `--summary`, `--update`, `--add-sources`, `--remove-sources`); data in `00_Master/study_units.json`; organizational only (no AI synthesis)
- `study_unit_dashboard.py` — unit dashboard and unit review plans (`--unit-id`, `--export`, `--review-plan`, optional `--limit`, `--overwrite`, `--json`); exports under `08_App_Data/reports/study_units/`; unit plans under `07_My_Work/review_sessions/UNIT-XXXX_YYYY-MM-DD_*`
- `unit_synthesis_packet.py` — export unit synthesis packet for manual AI synthesis (`--course`, `--unit-id`, optional `--overwrite`, `--no-learning-state`, `--json`); Markdown + metadata JSON under `08_App_Data/reports/study_units/UNIT-XXXX_synthesis_packet.*`; no API call; GUI **Study Units** → **Unit Synthesis Packet**
- `import_unit_synthesis.py` — import versioned unit synthesis Markdown (`--course`, `--unit-id`, `--file` or `--text`, optional `--synthesizer-name`, `--notes`); files under `06_Study_Outputs/study_units/UNIT-XXXX/`; registry `UNIT-XXXX_synthesis_registry.json`; deterministic quality heading check; GUI **Study Units** → **Import Unit Synthesis**
- `generate_unit_study_pack.py` — generate unit study pack from latest synthesis (`--course`, `--unit-id`, optional `--overwrite`, `--diagnose-only`, `--json`); outputs `UNIT-XXXX_unit_study_guide.md`, flashcards, quiz, active recall, formula sheet, manifest; GUI **Study Units** → **Unit Study Pack**
- `unit_review.py` — unit-level active recall and flashcard review (`--list-recall`, `--record-recall`, `--list-flashcards`, `--record-flashcard`, `--summary`); logs under `07_My_Work/unit_active_recall_logs/` and `07_My_Work/unit_flashcard_logs/` (separate from source-level logs); lightweight due dates for unit flashcards; feeds unit study sessions and unit review plans
- `pipeline_status.py` — pipeline checklist and next recommended step (`--course`, `--source-id`)
- `run_next_step.py` — run one guided Pipeline Doctor step (`--course`, `--source-id`; optional `--overwrite`, `--base-url`, `--model`, `--max-tokens`, `--max-words`, `--overlap-words`, `--full-digest`, `--only-needs-review`)

- `init_studyforge_structure.py` — idempotent project scaffold (folders + placeholders)
- `create_course.py` — create a new course from `_Course_Template` (`--code`, `--name`, `--list`)
- `add_source.py` — copy source files into a course (`--course`, `--type`, `--file`, `--title`, `--list`)
- `extract_source.py` — extract text from a registered PDF (`--course`, `--source-id`, optional `--overwrite`); auto-runs extraction quality check after extraction
- `check_extraction_quality.py` — analyze extracted text quality (`--course`, `--source-id`, optional `--json`); reports under `02_Extracted_Text/extraction_logs/`; no OCR/AI; GUI **Pipeline** → **Extraction Quality**
- `chunk_source.py` — chunk extracted Markdown (`--course`, `--source-id`, optional `--max-words`, `--overlap-words`, `--overwrite`)
- `check_lm_studio.py` — verify LM Studio API at `http://localhost:1234/v1`
- `run_local_digest.py` — LM Studio digest per chunk (`--course`, `--source-id`, optional `--limit-chunks`, `--overwrite`, `--model`)
- `review_local_digest.py` — rule-based digest quality review (`--course`, `--source-id`, optional `--min-words`)
- `export_intermediate_audit_packet.py` — export packet for Gemini/AI Studio (`--course`, `--source-id`, optional `--limit-chunks`, `--only-needs-review`, `--overwrite`)
- `run_intermediate_audit.py` — automated intermediate audit via Google AI/Gemma 4 (`--course`, `--source-id`, optional `--model`, `--keep-raw` for debug raw outputs). Responses are cleaned by `src/studyforge/audits/audit_sanitizer.py` (`sanitize_audit_output`) before save to remove scratchpad/reasoning noise; tests in `tests/test_audit_sanitizer.py`
- `import_intermediate_audit.py` — import manual audit from Gemini (`--course`, `--source-id`, `--file` or `--text`, optional `--auditor-name`, `--notes`)
- `export_final_audit_packet.py` — export packet for ChatGPT final audit (`--course`, `--source-id`, optional `--limit-chunks`, `--only-needs-review`, `--overwrite`)
- `import_final_audit.py` — import manual final audit (`--course`, `--source-id`, `--file` or `--text`, optional `--auditor-name`, `--notes`)
- `normalize_final_audit.py` — deterministic final audit heading normalizer (`--course`, `--source-id`, optional `--overwrite`, `--import-as-new-version`, `--export-repair-packet`, `--audit-version`); writes `05_Final_Audits/<SRC>/<SRC>_final_audit_normalized.md` and report JSON; repair packet for manual ChatGPT. GUI **Audits** → **Final Audit Normalizer**
- `generate_study_pack.py` — build study guide, flashcards (Markdown + CSV + Anki TSV), formula sheet, practice quiz, active recall, and weak-points seed from latest final audit (`--course`, `--source-id`, optional `--overwrite`, `--diagnose-only`); no AI; instant generation is normal; manifest includes quality report and `flashcard_count`. GUI **Pipeline** → **Study Pack**
- `export_flashcards.py` — regenerate flashcard exports only from the latest final audit (`--course`, `--source-id`, optional `--overwrite`); writes Markdown, CSV, and Anki TSV under `06_Study_Outputs/flashcards/`; GUI **Pipeline** → **Flashcards** export section
- `today.py` — Today dashboard summary (`--course`, optional `--export`); aggregates due flashcards, recall gaps, mistakes, weak points, review plan, and session status; exports under `07_My_Work/today_dashboard/`; GUI **Today** page (default)
- `course_quality.py` — course-level trust/readiness report across all sources (`--course`, optional `--export`, `--json`); exports under `08_App_Data/reports/`; GUI **Course Quality** page
- `evidence_trace.py` — inspect source/digest/audit evidence chain (`--course`, `--source-id`, `--summary`, `--chunks`, `--chunk-id`, `--export`); exports under `08_App_Data/reports/evidence_traces/`; GUI **Evidence Trace** page
- `backup_course.py` — local course backup zip (`--course`, optional `--no-sources`, `--output-dir`, `--list`, `--overwrite`); default output `08_App_Data/exports/backups/`; includes `STUDYFORGE_BACKUP_INFO.md`; no cloud upload; GUI **Courses** → **Course backup**
- `verify_backup.py` — verify backup zip structure (`--file`), dry-run restore preview (`--preview-restore`), safe restore to new folder only (`--restore-as`); never overwrites existing courses; GUI **Courses** → **Backup verification**
- `flashcards_review.py` — self-graded flashcard review with lightweight due scheduling (`--list`, `--record`, `--summary`, `--due`); logs under `07_My_Work/flashcard_logs/` with `due_date` per review; GUI **Flashcards** page
- `mock_test.py` — deterministic mock tests from study packs (`--generate` with `--source-id` or `--unit-id`, `--record`, `--summary`; optional `--questions`, `--no-flashcards`); outputs under `07_My_Work/mock_tests/`; attempts in `mock_test_attempts.json`; no AI grading; GUI **Mock Tests** page
- `exam_targets.py` — manage exam targets (`--list`, `--create`, `--update`, `--summary`); data in `00_Master/exam_targets.json`; validates units/sources; GUI **Exam Prep**
- `exam_prep.py` — generate deterministic exam prep plans (`--exam-id`, optional `--export`, `--overwrite`, `--json`); outputs under `07_My_Work/exam_prep/`; no AI or calendar integration
- `active_recall.py` — list questions, record self-graded attempts, export summary (`--list`, `--record`, `--summary`); optional `--create-mistake`, `--create-weak-point`, `--weak-point-concept` on `--record`; logs under `07_My_Work/active_recall_logs/`; GUI **Active Recall** page
- `mistakes.py` — course mistakes log (`--list`, `--add`, `--update-status`, `--export`); files `07_My_Work/mistakes_log.json` / `mistakes_log.md`
- `weak_points.py` — weak points tracker (`--list`, `--add`, `--update`, `--export`); files `07_My_Work/weak_points.json` / `weak_points.md`; GUI **Review Tracker** page
- `review_plan.py` — generate daily review plan Markdown + JSON (`--course`, optional `--date`, `--limit`, `--overwrite`); output under `07_My_Work/review_sessions/`; GUI **Review Tracker** → **Review Session Planner**
- `study_session.py` — guided study session from review priorities plus unanswered active recall from study packs (`--course`, `--start`, optional `--unit-id` for unit-focused scope, optional `--exam-id` for exam-target scope, `--latest`, `--session-id`, `--complete-item`, `--result`, `--finish`, `--export`); logs under `07_My_Work/study_sessions/`; GUI **Study Session** (course-wide, study unit, or exam target)
- `exam_readiness.py` — deterministic exam readiness score for an exam target (`--course`, `--exam-id`, optional `--export`, `--overwrite`, `--json`); reports under `07_My_Work/exam_prep/`; GUI **Exam Prep** (readiness section)
- `grade_mock_test.py` — per-question mock test grading (`--list`, `--mock-test-id`, `--questions`, `--grade-question`, `--grade`, `--summary`, `--finalize`, `--export-review`); grading under `07_My_Work/mock_tests/graded/`; GUI **Mock Tests** (Detailed Grading)
