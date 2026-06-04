# scripts

Utility and setup scripts.

- `launch_gui.py` — start Streamlit GUI (`app.py`)
- `pipeline_status.py` — pipeline checklist and next recommended step (`--course`, `--source-id`)

- `init_studyforge_structure.py` — idempotent project scaffold (folders + placeholders)
- `create_course.py` — create a new course from `_Course_Template` (`--code`, `--name`, `--list`)
- `add_source.py` — copy source files into a course (`--course`, `--type`, `--file`, `--title`, `--list`)
- `extract_source.py` — extract text from a registered PDF (`--course`, `--source-id`, optional `--overwrite`)
- `chunk_source.py` — chunk extracted Markdown (`--course`, `--source-id`, optional `--max-words`, `--overlap-words`, `--overwrite`)
- `check_lm_studio.py` — verify LM Studio API at `http://localhost:1234/v1`
- `run_local_digest.py` — LM Studio digest per chunk (`--course`, `--source-id`, optional `--limit-chunks`, `--overwrite`, `--model`)
- `review_local_digest.py` — rule-based digest quality review (`--course`, `--source-id`, optional `--min-words`)
- `export_intermediate_audit_packet.py` — export packet for Gemini/AI Studio (`--course`, `--source-id`, optional `--limit-chunks`, `--only-needs-review`, `--overwrite`)
- `run_intermediate_audit.py` — automated intermediate audit via Google AI/Gemma 4 (`--course`, `--source-id`, optional `--model`, `--keep-raw` for debug raw outputs); output is sanitized to remove scratchpad/reasoning noise
- `import_intermediate_audit.py` — import manual audit from Gemini (`--course`, `--source-id`, `--file` or `--text`, optional `--auditor-name`, `--notes`)
- `export_final_audit_packet.py` — export packet for ChatGPT final audit (`--course`, `--source-id`, optional `--limit-chunks`, `--only-needs-review`, `--overwrite`)
- `import_final_audit.py` — import manual final audit (`--course`, `--source-id`, `--file` or `--text`, optional `--auditor-name`, `--notes`)
- `generate_study_pack.py` — build study guide, flashcards, quiz, and related files from latest final audit (`--course`, `--source-id`, optional `--overwrite`)
