# StudyForge

StudyForge is a local-first AI study pipeline for digesting source material,
creating study notes, auditing AI-generated outputs, generating study packs,
and tracking mistakes and weak points.

## Graphical interface (Streamlit)

Install dependencies and launch the GUI from the project root:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Or:

```bash
python scripts/launch_gui.py
```

The GUI wraps the same backend functions as the CLI scripts (courses, sources, pipeline, audits).

## Quick start (CLI)

Run the scaffold script (safe to re-run):

```bash
python scripts/init_studyforge_structure.py
```

Create a course from the template:

```bash
python scripts/create_course.py --code ECA1010 --name "Microeconomics"
python scripts/create_course.py --list
```

Add source material to a course:

```bash
python scripts/add_source.py --course ECA1010_Microeconomics --type textbook \
  --file "C:\path\to\book.pdf" --title "Main Textbook"
python scripts/add_source.py --course ECA1010_Microeconomics --list
```

Extract text from a registered PDF (requires PyMuPDF):

```bash
python -m pip install -r requirements.txt
python -c "import fitz; print('PyMuPDF OK')"
python scripts/extract_source.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/extract_source.py --course ECA1010_Microeconomics --source-id SRC-0001 --overwrite
```

Chunk extracted text into source packets:

```bash
python scripts/chunk_source.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/chunk_source.py --course ECA1010_Microeconomics --source-id SRC-0001 --max-words 1000 --overlap-words 100 --overwrite
```

Local digest via LM Studio (start LM Studio and load a model first):

```bash
python -m pip install -r requirements.txt
python scripts/check_lm_studio.py
python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1
python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Review local digest quality (no AI):

```bash
python scripts/review_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Check pipeline status and next recommended step:

```bash
python scripts/pipeline_status.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Export intermediate audit packet for manual Gemini / AI Studio review:

```bash
python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1 --overwrite
python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001 --only-needs-review --overwrite
```

Run automated intermediate audit (Google AI / Gemma 4; output is cleaned to remove scratchpad noise):

```bash
python scripts/run_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/run_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --keep-raw
```

Import Gemini intermediate audit (versioned storage):

```bash
python scripts/import_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\to\gemini_audit.md"
python scripts/import_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --text "Audit content" --notes "First pass"
```

Export final audit packet for manual ChatGPT review:

```bash
python scripts/export_final_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/export_final_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1 --overwrite
python scripts/export_final_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001 --only-needs-review --overwrite
```

Import ChatGPT final audit (versioned storage):

```bash
python scripts/import_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\to\final_audit.md"
python scripts/import_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --text "Final audit content" --notes "First pass"
```

Generate study pack from the latest final audit (no AI; deterministic parser):

```bash
python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001
python scripts/generate_study_pack.py --course ECA1010_Microeconomics --source-id SRC-0001 --overwrite
```

## Layout

- `config/` — application settings
- `courses/` — per-course data and pipeline outputs
- `docs/` — specifications and planning documents
- `prompts/` — LLM prompt templates
- `scripts/` — setup and utility scripts
- `src/studyforge/` — Python application code
- `app.py` — Streamlit GUI entry point
- `tests/` — automated tests

See each folder's README for details.
