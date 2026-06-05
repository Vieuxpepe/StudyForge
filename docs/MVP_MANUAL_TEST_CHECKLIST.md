# StudyForge MVP Manual Test Checklist

Use this checklist after code changes or before trusting StudyForge with a real course.
Work through one source end-to-end on your machine.

## Checklist

- [ ] Launch GUI
- [ ] Open **Today** page and confirm summary counts match your course data
- [ ] Create/select course
- [ ] Optional: create course backup (`python scripts/backup_course.py --course YourCourse` or **Courses** → **Course backup**); confirm zip under `08_App_Data/exports/backups/`; restore is manual in v1
- [ ] Upload/register a real PDF
- [ ] Confirm source appears in dashboard
- [ ] Try **Run next recommended step** on Pipeline (Guided Workflow) for one step
- [ ] Confirm Pipeline Doctor updates after the guided step
- [ ] Extract PDF
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
- [ ] Start a **Study Session** on the Study Session page (or `study_session.py --start`)
- [ ] Confirm session includes review-priority items and unanswered active recall from study packs (when available)
- [ ] Complete at least one session item (recall, unanswered recall, mistake, or weak point)
- [ ] Finish session and export summary under `07_My_Work/study_sessions/`
- [ ] Confirm priorities match your open mistakes / weak points / recall gaps / flashcards / unanswered recall

## Pass criteria

- No crashes
- Pipeline Doctor next action makes sense at each step
- Generated files exist on disk under the course folder
- Study pack files are usable (guide, flashcards Markdown/CSV/Anki TSV, quiz, active recall, weak-points seed)
- No private PDFs or course outputs committed to Git (`git status` should not list files under `courses/<YourCourse>/` except the template)

## GUI quick map

| Step | Where in GUI |
|------|----------------|
| What to study today | **Today** |
| Course | Sidebar + **Courses** |
| Course backup | **Courses** → **Course backup** |
| Source PDF | **Sources** |
| Guided next step | **Pipeline** → **Guided Workflow** |
| Extract / chunk / digest / review | **Pipeline** (manual controls) |
| Pipeline Doctor + study pack | **Pipeline** (top: Doctor; **Study Pack** section after final audit) |
| Intermediate/final audits, normalizer | **Audits** |
| Active recall practice | **Active Recall** |
| Flashcard review | **Flashcards** |
| Mistakes / weak points / review plan | **Review Tracker** |
| Guided study session | **Study Session** |
| LM Studio URL / tokens | **Pipeline** |
| Google API key | **Settings** |

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
