# courses

One folder per course. Each real course is a copy of `_Course_Template` with
its own `00_Master` metadata and pipeline folders `01`–`08`.

## Create a new course

From the project root:

```bash
python scripts/create_course.py --code ECA1010 --name "Microeconomics"
```

This creates `courses/ECA1010_Microeconomics` (code + sanitized name). The
script does not overwrite an existing folder.

List existing courses:

```bash
python scripts/create_course.py --list
```

## Add source material

Copy PDFs and other files into `01_Source_Material/<type>/` and register them in
`08_App_Data/source_registry.json`:

```bash
python scripts/add_source.py --course ECA1010_Microeconomics --type textbook \
  --file "C:\Users\you\Downloads\book.pdf" --title "Main Textbook"
```

Allowed `--type` values: `textbook`, `slides`, `homework`, `notes`, `extra_readings`.

List registered sources:

```bash
python scripts/add_source.py --course ECA1010_Microeconomics --list
```

Existing files in the course folder are never overwritten; duplicate names get
suffixes like `book_002.pdf`.

## Extract text from a PDF

After adding a PDF source, extract page-by-page text (PyMuPDF):

```bash
python -m pip install -r requirements.txt
python -c "import fitz; print('PyMuPDF OK')"
python scripts/extract_source.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Outputs:

- `02_Extracted_Text/extracted_sources/SRC-0001_extracted_text.md`
- `02_Extracted_Text/extraction_logs/SRC-0001_extraction_log.json`

Use `--overwrite` to replace existing extraction files. Registry `status` becomes `extracted`.

## Chunk extracted text

After extraction, split text into page-aware chunks:

```bash
python scripts/chunk_source.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Outputs under `02_Extracted_Text/chunks/SRC-0001/` (chunk `.md` files + `chunk_manifest.json`).
Registry `status` becomes `chunked`.

## Local digest (LM Studio)

Requires LM Studio running at `http://localhost:1234/v1` with a model loaded:

```bash
python scripts/check_lm_studio.py
python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001 --limit-chunks 1
python scripts/run_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Outputs: `03_Local_Digests/SRC-0001/` and `08_App_Data/job_logs/SRC-0001_local_digest_log.json`.

## Review local digest quality

Rule-based check before cloud audits (no AI):

```bash
python scripts/review_local_digest.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Writes `SRC-0001_local_digest_review.md` and `.json` under `03_Local_Digests/SRC-0001/`.

## Export intermediate audit packet

Build a Markdown packet to paste into Gemini / Google AI Studio:

```bash
python scripts/export_intermediate_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Outputs under `04_Intermediate_Audits/SRC-0001/` (`*_intermediate_audit_packet.md` and `.json`).

## Import intermediate audit

Save Gemini (or other) audit results back into StudyForge:

```bash
python scripts/import_intermediate_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\gemini_audit.md"
```

Creates versioned files like `SRC-0001_intermediate_audit_v001.md` and updates `SRC-0001_intermediate_audit_registry.json`.

## Export final audit packet

After importing an intermediate audit, build a ChatGPT-ready final packet:

```bash
python scripts/export_final_audit_packet.py --course ECA1010_Microeconomics --source-id SRC-0001
```

Outputs under `05_Final_Audits/SRC-0001/` (`*_final_audit_packet.md` and `.json`).

## Import final audit

Save ChatGPT (or other) final audit results:

```bash
python scripts/import_final_audit.py --course ECA1010_Microeconomics --source-id SRC-0001 --file "C:\path\final_audit.md"
```

Creates `SRC-0001_final_audit_v001.md` and `SRC-0001_final_audit_registry.json`.

## Manual copy (optional)

You can still copy `_Course_Template` by hand, but the script sets
`course_profile.md` and `pipeline_settings.json` for you.
