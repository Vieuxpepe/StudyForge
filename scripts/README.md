# scripts

Utility and setup scripts.

- `launch_gui.py` — start Streamlit GUI (`app.py`)
- `pipeline_status.py` — pipeline checklist and next recommended step (`--course`, `--source-id`)
- `run_next_step.py` — run one guided Pipeline Doctor step (`--course`, `--source-id`; optional `--overwrite`, `--base-url`, `--model`, `--max-tokens`, `--max-words`, `--overlap-words`, `--full-digest`, `--only-needs-review`)

- `init_studyforge_structure.py` — idempotent project scaffold (folders + placeholders)
- `create_course.py` — create a new course from `_Course_Template` (`--code`, `--name`, `--list`)
- `add_source.py` — copy source files into a course (`--course`, `--type`, `--file`, `--title`, `--list`)
- `extract_source.py` — extract text from a registered PDF (`--course`, `--source-id`, optional `--overwrite`)
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
- `generate_study_pack.py` — build study guide, flashcards, formula sheet, practice quiz, active recall, and weak-points seed from latest final audit (`--course`, `--source-id`, optional `--overwrite`, `--diagnose-only`); no AI; instant generation is normal; manifest includes quality report. GUI **Pipeline** → **Study Pack**
- `active_recall.py` — list questions, record self-graded attempts, export summary (`--list`, `--record`, `--summary`); optional `--create-mistake`, `--create-weak-point`, `--weak-point-concept` on `--record`; logs under `07_My_Work/active_recall_logs/`; GUI **Active Recall** page
- `mistakes.py` — course mistakes log (`--list`, `--add`, `--update-status`, `--export`); files `07_My_Work/mistakes_log.json` / `mistakes_log.md`
- `weak_points.py` — weak points tracker (`--list`, `--add`, `--update`, `--export`); files `07_My_Work/weak_points.json` / `weak_points.md`; GUI **Review Tracker** page
- `review_plan.py` — generate daily review plan Markdown + JSON (`--course`, optional `--date`, `--limit`, `--overwrite`); output under `07_My_Work/review_sessions/`; GUI **Review Tracker** → **Review Session Planner**
- `study_session.py` — guided study session from review priorities (`--course`, `--start`, `--latest`, `--session-id`, `--complete-item`, `--result`, `--finish`, `--export`); logs under `07_My_Work/study_sessions/`; GUI **Study Session**
