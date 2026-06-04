# StudyForge Regression / Logic / Overlap Audit

Audit date: 2026-06-04 (stabilization pass). Scope: static review of pipeline status, parsers, CLI/GUI, privacy, and targeted regression tests. No new user-facing features.

---

## Scope

Reviewed:

- `src/studyforge/core/` — pipeline status, guided workflow, extraction/chunking/digest jobs, sources
- `src/studyforge/audits/` — final/intermediate import, normalizer, packets, sanitizer
- `src/studyforge/study/` — study pack, active recall, mistakes, weak points, review planner
- `src/studyforge/ui/` — Streamlit app, helpers
- `scripts/*.py` — CLI entry points
- `.gitignore`, `README.md`, `scripts/README.md`, `docs/MVP_MANUAL_TEST_CHECKLIST.md`
- Test suite under `tests/`

Out of scope (by design): SQLite, vector search, autonomous agents, AI grading, large refactors.

---

## Findings

### Critical

None identified that would corrupt data silently without user action. Automated intermediate audit and manual imports remain separate code paths.

### Important

| Finding | Risk | Fix / recommendation | Test |
|--------|------|----------------------|------|
| **Registry vs artifacts drift after final re-import** | Re-importing a final audit at `study_pack_generated` sets registry to `final_audit_imported` but leaves old study-pack paths/manifest on disk. | **Fix applied:** `import_final_audit` warns when prior status was `study_pack_generated`. **Pipeline Doctor** compares `based_on_final_audit_id` in the study pack manifest to `latest_final_audit_id` in the registry; warns and recommends **Regenerate study pack** when they differ. Step `study_pack_generated` stays done. | `test_stale_study_pack_warning_and_regenerate_action`, `test_stale_study_pack_suggests_regenerate`, `test_reimport_warns_stale_study_pack` |
| **Re-normalizing a flattened audit (V002)** | Running normalizer on an already-flattened audit cannot recover `###` content moved to Additional Notes. | Use `--audit-version 1` (or original audit) when re-normalizing. Documented in audit assumptions. | `test_normalized_import_after_study_pack_generated` (nested source) |
| **Intermediate re-import blocked after final audit** | `import_intermediate_audit` only allows digest statuses + `intermediate_audit_imported`. Cannot add IA version after `final_audit_imported` / `study_pack_generated`. | By design for MVP; use manual file edit or earlier snapshot if truly needed. | No change |
| **Duplicate Markdown heading helpers** | `final_audit_normalizer.py` and `study_pack.py` each define `_heading_level` / section parsing. Logic must stay aligned. | **No refactor.** Headings lists tested for parity. Parser behavior covered by shared regression tests. | `test_normalizer_and_study_pack_headings_match`, nested parsing tests |
| **GUI normalizer lacks `--audit-version`** | CLI supports `--audit-version`; Audits GUI always uses latest audit. | Document CLI flag; optional future GUI dropdown. | — |

### Minor

| Finding | Risk | Fix / recommendation | Test |
|--------|------|----------------------|------|
| **`source_pipeline_flags` omitted `study_pack_generated`** | Dashboard flags could show `final_audit: no` despite completed pipeline. | **Fix applied:** include `study_pack_generated` in status sets. | `test_gui_flags_include_study_pack_generated` |
| **`export_or_run_intermediate_audit` naming** | Label suggests automated run; guided workflow only exports packet. | Warnings already in guided workflow + Pipeline hint when Google key set. | `test_maps_export_intermediate` (existing) |
| **`_determine_next_action(..., warnings)` unused parameter** | Dead code; no runtime bug. | Leave as-is (minimal change policy). | — |
| **Chunking allows any status except `added`** | Could re-chunk after study pack if paths exist. | Acceptable; overwrite flags gate destructive reruns. | — |
| **Active recall / mistakes do not update source status** | Correct; tracking is separate from pipeline registry. | No action | — |

### No action needed

- `extract_markdown_section` already stops at next `##`, not `###` — correct Markdown behavior.
- `parse_top_level_markdown_sections` (normalizer) matches that rule for `##` parents.
- `EXPECTED_FINAL_AUDIT_HEADINGS` values match `study_pack._SECTION_HEADINGS` labels.
- Repair packet uses the same heading list as the normalizer / study pack.
- Guided workflow `RUNNABLE_ACTION_KEYS` excludes Google intermediate audit.
- `.gitignore` ignores `courses/*` with template exceptions and secrets paths.
- GitHub Actions runs `unittest discover -s tests`.

---

## Status Flow Review

### Source registry statuses (writers)

| Status | Typical setter |
|--------|----------------|
| `added` | `add_source` |
| `extracted` | `extract_registered_source` |
| `chunked` | `chunk_registered_source` |
| `local_digest_partial` / `local_digest_complete` | `run_local_digest_for_source` |
| `intermediate_audit_imported` | `import_intermediate_audit` |
| `final_audit_imported` | `import_final_audit` |
| `study_pack_generated` | `generate_study_pack` |

### Expected happy path

```
added → extracted → chunked → local_digest_* → intermediate_audit_imported
  → final_audit_imported → study_pack_generated
```

### Valid side paths

- **Final re-import** at `study_pack_generated` → registry becomes `final_audit_imported` (+ warning); regenerate study pack to refresh outputs.
- **Normalized final import** (StudyForge Normalizer) → new version file; same registry rules as manual import.
- **Study pack regenerate** → `overwrite=True`; status stays `study_pack_generated`.
- **Active recall / mistakes / weak points / review plans** → files under `07_My_Work/`; do not change registry status.

### Pipeline Doctor vs registry

- **Steps** are artifact-based (files on disk).
- **`next_action`** keys: `extract_pdf`, `chunk_source`, `run_local_digest`, `review_local_digest`, `export_or_run_intermediate_audit`, `export_final_audit_packet`, `generate_study_pack`, `study_pack_ready`, `source_missing`.
- Registry status is reported but does not alone determine `next_action`.

---

## Parser / Normalizer Review

### Rules (aligned)

1. A `##` section includes all content until the next `##` (or `#`).
2. `###` and deeper headings are **content inside** the parent `##`, not separate top-level sections.
3. Study pack extraction uses the same stop rule (`level <= section_level` ends section).
4. Normalizer maps only top-level `##` headings; nested `###` stay in mapped section bodies.
5. Unmatched top-level `##` only → `## Additional Notes From Original Audit`.

### Placeholders

- Normalizer missing text: `Not found in original final audit.`
- Study pack missing text: `Not found in final audit.`

### Sanitizer

- Applies to **automated** Google intermediate audit responses before save.
- Manual final/intermediate imports are stored as provided (no sanitizer on final audit).

---

## CLI / GUI Review

| Feature | CLI | GUI | Notes |
|---------|-----|-----|-------|
| Extract / chunk / digest / review | Yes | Pipeline | Aligned |
| Intermediate packet / import | Yes | Audits | Automated IA: CLI + Audits (not guided) |
| Final packet / import | Yes | Audits | Aligned |
| Final normalizer / repair packet | Yes | Audits | GUI lacks `--audit-version` |
| Study pack + diagnose | Yes | Pipeline | `--diagnose-only` CLI only |
| Active recall / mistakes / weak points / review plan | Yes | Dedicated pages | Aligned |
| Guided next step | `run_next_step.py` | Pipeline | Default 1-chunk digest; `--full-digest` for all |
| Pipeline status | `pipeline_status.py` | Pipeline | Aligned |

**Overwrite:** Study pack, normalizer, repair packet, and most jobs respect `overwrite` / refusal patterns consistently.

**Quality warnings:** Study pack and normalizer surface weak quality; GUI shows banners on Pipeline / Audits.

---

## Privacy Review

- `.gitignore` ignores `courses/*` except `courses/README.md` and `courses/_Course_Template/**`.
- Secrets: `.env`, `*.env`, `config/local_secrets.json`.
- Registries under gitignored course folders store **absolute local paths** — safe for public repo if course data is not force-added.
- **Caveat:** `git add -f courses/...` can still expose private data; documented in README.

---

## Remaining Known Risks

- PDF extraction quality varies by PDF engine and document layout.
- LM Studio / Google outputs can be incomplete or noisy; sanitizer helps intermediate automation only.
- Study pack quality depends on final audit heading structure; use normalizer or repair packet when weak.
- Manual imports can bypass intermediate sanitizer.
- Registry/path drift possible if files are deleted manually outside StudyForge.
- Re-normalizing a previously flattened audit cannot restore nested structure from Additional Notes automatically.

---

## Fixes Applied (this pass)

1. `source_pipeline_flags` — recognize `study_pack_generated`.
2. `import_final_audit` — warn when re-importing after `study_pack_generated`.
3. `README.md` — document absolute paths in local registries.
4. `tests/test_regression_stability.py` — high-value regression coverage.
5. `tests/test_final_import.py` — stale study pack warning test.
6. `pipeline_status.py` — stale study pack detection (manifest vs `latest_final_audit_id`).

---

## Recommended Next Actions (optional, not implemented)

- GUI: audit version selector for normalizer.
- ~~Pipeline warning when manifest audit ID ≠ latest final audit ID~~ — **implemented** (stale study pack detection).
- Shared `markdown_sections.py` helper if a third consumer appears (avoid premature abstraction).
- Clear or annotate stale study-pack registry fields on final re-import (behavior change — needs explicit UX decision).
