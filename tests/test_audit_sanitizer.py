"""Tests for audit output sanitizer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.audits.audit_sanitizer import (  # noqa: E402
    sanitize_audit_output,
    sanitize_audit_output_with_stats,
)

NOISY_PREFIX = """Wait, let me check the formula again.
Self-Correction: I should verify page 20.
Final Plan: output issues only.
*   *Wait, one more thing.
Let's re-read the source.

"""

CLEAN_AUDIT = """## Audit — SRC-0001-CHUNK-0001

### Issue 1

**Original claim:**
The digest says X.

**Verdict:** Wrong

**Corrected version:**
The source says Y.

**Source support:**
Page 12.

**Why this matters:**
Exam trap on inflation rate.
"""


class TestAuditSanitizer(unittest.TestCase):
    def test_removes_scratchpad_lines(self) -> None:
        text = NOISY_PREFIX + CLEAN_AUDIT
        cleaned = sanitize_audit_output(text)
        self.assertNotIn("Wait, let me check", cleaned)
        self.assertNotIn("Self-Correction", cleaned)
        self.assertNotIn("Final Plan", cleaned)
        self.assertIn("## Audit — SRC-0001-CHUNK-0001", cleaned)

    def test_preserves_structured_audit(self) -> None:
        cleaned = sanitize_audit_output(CLEAN_AUDIT)
        self.assertIn("### Issue 1", cleaned)
        self.assertIn("**Verdict:** Wrong", cleaned)
        self.assertIn("**Corrected version:**", cleaned)
        self.assertIn("**Source support:**", cleaned)
        self.assertIn("**Why this matters:**", cleaned)

    def test_clean_report_unchanged(self) -> None:
        cleaned = sanitize_audit_output(CLEAN_AUDIT)
        self.assertIn("No major issues found", sanitize_audit_output(
            "## Audit — SRC-0001-CHUNK-0002\n\nNo major issues found.\n\n"
            "### Minor improvements\n\n* Add page refs.\n"
        ))
        self.assertGreater(len(cleaned), 50)

    def test_stats_track_removal(self) -> None:
        text = NOISY_PREFIX + CLEAN_AUDIT
        cleaned, stats = sanitize_audit_output_with_stats(text)
        self.assertGreater(stats["sanitizer_removed_words"], 0)
        self.assertGreater(stats["sanitizer_removed_characters"], 0)
        self.assertGreater(stats["raw_word_count"], stats["cleaned_word_count"])
        self.assertEqual(stats["cleaned_word_count"], len(cleaned.split()))

    def test_nested_bullet_wait_removed(self) -> None:
        text = (
            "*   *Wait, let me check IPC.\n"
            "## Audit — SRC-0001-CHUNK-0003\n\n"
            "### Issue 1\n\n**Verdict:** Correct\n"
        )
        cleaned = sanitize_audit_output(text)
        self.assertNotIn("*Wait", cleaned)
        self.assertIn("## Audit — SRC-0001-CHUNK-0003", cleaned)


if __name__ == "__main__":
    unittest.main()
