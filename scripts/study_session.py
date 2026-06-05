#!/usr/bin/env python3
"""
Study Session Mode v1 — guided review through priorities and unanswered recall (no AI).

Examples:
    python scripts/study_session.py --course ECA1010_Microeconomics --start --limit 10
    python scripts/study_session.py --course ECA1010_Microeconomics --start --unit-id UNIT-0001 --limit 10
    python scripts/study_session.py --course ECA1010_Microeconomics --start --exam-id EXAM-0001 --limit 20
    python scripts/study_session.py --course ECA1010_Microeconomics --latest
    python scripts/study_session.py --course ECA1010_Microeconomics --session-id SESSION-20260604-120000 --complete-item SESSION-ITEM-0001 --result partial --notes "Still confused"
    python scripts/study_session.py --course ECA1010_Microeconomics --session-id SESSION-20260604-120000 --finish
    python scripts/study_session.py --course ECA1010_Microeconomics --session-id SESSION-20260604-120000 --export
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from studyforge.core.sources import CourseNotFoundError  # noqa: E402
from studyforge.study.exam_targets import ExamTargetNotFoundError  # noqa: E402
from studyforge.study.study_session import (  # noqa: E402
    ConflictingSessionScopeError,
    InvalidSessionResultError,
    StudySessionItemNotFoundError,
    StudySessionNotFoundError,
    complete_study_session,
    export_study_session_summary,
    get_latest_study_session,
    record_session_item_result,
    start_study_session,
)
from studyforge.study.study_units import StudyUnitNotFoundError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guided study session from review priorities and unanswered recall (no AI)."
    )
    parser.add_argument("--course", required=True)
    parser.add_argument("--start", action="store_true", help="Start a new session.")
    parser.add_argument("--limit", type=int, default=10, help="Max items (with --start).")
    parser.add_argument(
        "--unit-id",
        help="Start a unit-focused session (sources in this study unit only).",
    )
    parser.add_argument(
        "--exam-id",
        help="Start an exam-focused session (units and sources in the exam target).",
    )
    parser.add_argument("--latest", action="store_true", help="Show latest session JSON.")
    parser.add_argument("--session-id", help="Session id for item/finish/export.")
    parser.add_argument("--complete-item", help="Session item id to mark done.")
    parser.add_argument("--result", help="Result grade or status.")
    parser.add_argument("--notes", default="", help="Notes or answer text.")
    parser.add_argument("--answer", default="", help="Answer text for active recall items.")
    parser.add_argument(
        "--create-mistake",
        action="store_true",
        help="For weak recall grades: also add mistake.",
    )
    parser.add_argument(
        "--create-weak-point",
        action="store_true",
        help="For weak recall grades: also add weak point.",
    )
    parser.add_argument("--weak-point-concept", default="")
    parser.add_argument("--confidence", type=int, default=None, help="Weak point confidence 1-5.")
    parser.add_argument("--finish", action="store_true", help="Mark session complete.")
    parser.add_argument("--export", action="store_true", help="Export session summary Markdown.")
    return parser


def _print_latest(session: dict) -> None:
    print("Latest study session\n")
    print(f"Session: {session.get('session_id')}\n")
    print(f"Status: {session.get('status')}\n")
    print(f"Items: {len(session.get('items', []))}")
    print(f"Completed: {len(session.get('completed_items', []))}\n")
    if session.get("items"):
        print("Queue:")
        for item in session["items"]:
            print(
                f"  - {item.get('session_item_id')} "
                f"({item.get('type')}): {item.get('title', '')[:60]}"
            )
        print()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.start:
            if args.unit_id and args.exam_id:
                print(
                    "Error: Provide either --unit-id or --exam-id, not both.",
                    file=sys.stderr,
                )
                return 1
            summary = start_study_session(
                args.course,
                limit=args.limit,
                unit_id=args.unit_id,
                exam_id=args.exam_id,
            )
            print("Study session started.\n")
            print(f"Scope:\n{summary.get('scope', 'course')}\n")
            if summary.get("scope") == "unit":
                print(
                    f"Unit:\n{summary.get('unit_id', '')} — "
                    f"{summary.get('unit_title', '')}\n"
                )
            elif summary.get("scope") == "exam":
                print(
                    f"Exam:\n{summary.get('exam_id', '')} — "
                    f"{summary.get('exam_title', '')}\n"
                )
                print(f"Date:\n{summary.get('exam_date', '')}\n")
                if summary.get("target_score") is not None:
                    print(f"Target:\n{summary.get('target_score')}%\n")
            print(f"Session: {summary['session_id']}\n")
            print(f"Items: {summary['item_count']}\n")
            if summary.get("warning"):
                print(f"Warning: {summary['warning']}\n")
            print(f"Log: {summary['log_path']}\n")
            return 0

        if args.latest:
            session = get_latest_study_session(args.course)
            if session is None:
                print("No study sessions found for this course.", file=sys.stderr)
                return 1
            _print_latest(session)
            return 0

        if not args.session_id:
            print("Error: --session-id is required for this action.", file=sys.stderr)
            return 1

        if args.complete_item:
            if not args.result:
                print("Error: --result is required with --complete-item.", file=sys.stderr)
                return 1
            summary = record_session_item_result(
                args.course,
                args.session_id,
                args.complete_item,
                args.result,
                notes=args.notes or None,
                user_answer=args.answer or None,
                create_mistake=args.create_mistake,
                create_weak_point=args.create_weak_point,
                weak_point_concept=args.weak_point_concept or None,
                confidence_level=args.confidence,
            )
            print("Session item recorded.\n")
            print(f"Item: {summary['session_item_id']}\n")
            print(f"Result: {summary['result']}\n")
            print(
                f"Progress: {summary['completed_count']}/{summary['item_count']}\n"
            )
            return 0

        if args.finish:
            summary = complete_study_session(args.course, args.session_id)
            print("Study session finished.\n")
            print(f"Session: {summary['session_id']}\n")
            print(f"Completed: {summary['completed_count']}/{summary['item_count']}\n")
            return 0

        if args.export:
            path = export_study_session_summary(args.course, args.session_id)
            print("Session summary exported.\n")
            print(f"Path: {path}\n")
            return 0

        print(
            "Error: specify --start, --latest, --complete-item, --finish, or --export.",
            file=sys.stderr,
        )
        return 1

    except CourseNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (StudySessionNotFoundError, StudySessionItemNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except StudyUnitNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ExamTargetNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ConflictingSessionScopeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except InvalidSessionResultError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
