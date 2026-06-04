# studyforge (package)

Python source for the StudyForge pipeline and UI.

| Module      | Purpose (planned)                          |
|-------------|--------------------------------------------|
| `core`      | Shared types, config loading, utilities    |
| `extraction`| PDF/text extraction from source material   |
| `chunking`  | Splitting sources into model-sized chunks  |
| `llm`       | Local and cloud LLM clients                |
| `audits`    | Intermediate and final audit runners       |
| `study`     | Study pack generation (guides, cards, etc.) |
| `storage`   | SQLite and file-backed persistence (later) |
| `ui`        | Streamlit or other local UI (later)        |
