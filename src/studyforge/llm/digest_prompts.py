"""
Prompt templates for local LM Studio digests.
"""

from __future__ import annotations

SYSTEM_MESSAGE = """You are StudyForge's local study digest assistant.

Your job is to digest source material carefully and conservatively.

Rules:
* Do not invent facts.
* Do not over-compress.
* Preserve source references.
* Mark uncertainty.
* Explain clearly.
* If a section has no supported content in this chunk, write exactly: Not verified in this chunk.
* Focus on helping the student understand and study.
* You MUST output every required ## section through ## Source References. Never stop early."""


def build_local_digest_messages(
    chunk_markdown: str,
    course_name: str,
    source_id: str,
    chunk_id: str,
) -> list[dict]:
    """
    Build OpenAI-style chat messages for a single chunk digest.

    The model is asked to produce a structured Markdown digest with fixed sections.
    """
    user_content = f"""Course: {course_name}
Source ID: {source_id}
Chunk ID: {chunk_id}

Chunk text:

{chunk_markdown}

---

Produce a structured study digest in Markdown with exactly these sections (use the headings shown):

# Local Digest for {chunk_id}

## Big Picture

## Key Ideas

## Definitions

## Formulas / Rules / Methods

## Step-by-Step Procedures

## Worked Examples from the Source

## New Practice Examples

## Common Mistakes / Traps

## Things to Memorize

## Things to Understand Deeply

## Flashcards

## Practice Questions

## Uncertain Claims

## Source References

Fill every section in order. Keep sections concise if needed, but include every heading.
If a section has no supported content in this chunk, write only: Not verified in this chunk.
Do not end the response until ## Source References is complete.
"""

    return [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": user_content},
    ]
