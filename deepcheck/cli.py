"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .claims import extract_claims
from .config import load_config
from .llm import Client
from .models import RATING_LABELS, RATINGS, Report
from .report import to_html, to_json, to_markdown
from .transcript import (
    TranscriptError,
    fetch_metadata,
    fetch_transcript,
    parse_video_id,
    to_text,
    watch_url,
    word_count,
)


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


COMMANDS = ("check", "transcribe")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deepcheck",
        description="Transcribe a YouTube video and fact-check what was said.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="transcribe and fact-check (default)")
    _add_check_args(check)

    transcribe = sub.add_parser("transcribe", help="fetch the transcript only")
    transcribe.add_argument("url", help="YouTube URL or video ID")
    transcribe.add_argument("-o", "--out", help="write to this file instead of stdout")
    transcribe.add_argument(
        "--timestamps", action="store_true", help="prefix each line with its timestamp"
    )
    return parser


def normalize_argv(argv: List[str]) -> List[str]:
    """Let `deepcheck <url>` mean `deepcheck check <url>`.

    Declaring the subcommand optional and repeating the `url` positional on the
    parent parser does not work: the parent's default re-clobbers whatever the
    subparser assigned. Rewriting argv keeps a single source of truth.

    The subcommand must be argv[0] — scanning for "the first non-flag token"
    would treat a flag's value (``--effort max``) as the subcommand slot.
    """
    if not argv or argv[0] in COMMANDS or argv[0] in ("-h", "--help"):
        return argv
    return ["check"] + argv


def _add_check_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("url", help="YouTube URL or video ID")
    parser.add_argument(
        "-o",
        "--out",
        default="report",
        help="output path without extension (default: report)",
    )
    parser.add_argument(
        "-f",
        "--format",
        default="md",
        help="comma-separated: md, html, json (default: md)",
    )
    parser.add_argument("--model", help="override the Claude model")
    parser.add_argument(
        "--max-claims", type=int, help="cap the number of claims verified"
    )
    parser.add_argument("--concurrency", type=int, help="parallel verifications")
    parser.add_argument(
        "--max-searches", type=int, help="web searches allowed per claim"
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="reasoning effort for verification",
    )
    parser.add_argument(
        "--no-fallbacks",
        action="store_true",
        help="disable server-side refusal fallback",
    )


def cmd_transcribe(args) -> int:
    cfg = load_config()
    video_id = parse_video_id(args.url)
    segments, source = fetch_transcript(video_id, cfg)

    if args.timestamps:
        body = "\n".join(f"[{s.formatted_time}] {s.text}" for s in segments)
    else:
        body = to_text(segments)

    if args.out:
        Path(args.out).write_text(body, encoding="utf-8")
        _log(f"Wrote {args.out} ({word_count(segments):,} words, via {source})")
    else:
        print(body)
    return 0


def cmd_check(args) -> int:
    cfg = load_config(
        model=getattr(args, "model", None),
        max_claims=getattr(args, "max_claims", None),
        concurrency=getattr(args, "concurrency", None),
        max_searches=getattr(args, "max_searches", None),
        verify_effort=getattr(args, "effort", None),
    )
    if getattr(args, "no_fallbacks", False):
        cfg.use_fallbacks = False

    video_id = parse_video_id(args.url)

    _log("Fetching transcript...")
    segments, source = fetch_transcript(video_id, cfg)
    words = word_count(segments)
    meta = fetch_metadata(video_id)
    title = meta.get("title") or video_id
    _log(f"  {words:,} words via {source} — {title}")

    client = Client(cfg)

    _log("Extracting claims...")
    claims = extract_claims(
        segments,
        client,
        cfg,
        on_progress=lambda i, n: _log(f"  chunk {i}/{n}"),
    )
    if not claims:
        _log("No checkable claims found.")
        return 1
    _log(f"  {len(claims)} claims to verify")

    # Imported here so `deepcheck transcribe` never pays for the thread pool.
    from .verify import verify_claims

    _log(f"Verifying (concurrency {cfg.concurrency})...")
    findings = verify_claims(
        claims,
        client,
        cfg,
        on_progress=lambda done, total: _log(f"  {done}/{total}"),
    )

    report = Report(
        video_id=video_id,
        video_url=watch_url(video_id),
        title=title,
        checked_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        word_count=words,
        findings=findings,
        model=cfg.model,
        transcript_source=source,
    )

    written = _write_outputs(report, args.out, args.format)
    _print_summary(report, written)
    return 0


def _write_outputs(report: Report, out: str, formats: str) -> List[str]:
    renderers = {"md": to_markdown, "html": to_html, "json": to_json}
    written: List[str] = []

    for fmt in [f.strip().lower() for f in formats.split(",") if f.strip()]:
        if fmt not in renderers:
            _log(f"  (skipping unknown format {fmt!r})")
            continue
        path = Path(f"{out}.{fmt}")
        path.write_text(renderers[fmt](report), encoding="utf-8")
        written.append(str(path))

    return written


def _print_summary(report: Report, written: List[str]) -> None:
    counts = report.counts()
    _log("")
    _log(f"Checked {len(report.findings)} claims:")
    for rating in RATINGS:
        if counts.get(rating):
            _log(f"  {RATING_LABELS[rating]:<24} {counts[rating]}")
    _log("")
    for path in written:
        _log(f"Wrote {path}")


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    if not raw:
        parser.print_help()
        return 2

    args = parser.parse_args(normalize_argv(raw))

    try:
        if args.command == "transcribe":
            return cmd_transcribe(args)
        return cmd_check(args)
    except TranscriptError as exc:
        _log(f"Transcript error: {exc}")
        return 1
    except KeyboardInterrupt:
        _log("\nInterrupted.")
        return 130
    except Exception as exc:  # noqa: BLE001 - turn API faults into readable output
        message = describe_api_error(exc)
        if message is None:
            raise
        _log(message)
        return 1


def describe_api_error(exc: Exception) -> Optional[str]:
    """Map an Anthropic SDK exception to an actionable message.

    Returns None for anything that isn't an API error, so unexpected exceptions
    still surface with a full traceback.
    """
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return None

    if isinstance(exc, anthropic.AuthenticationError):
        return (
            "Authentication failed. Set ANTHROPIC_API_KEY, or run `ant auth login`."
        )
    if isinstance(exc, anthropic.PermissionDeniedError):
        return f"Permission denied: {exc}"
    if isinstance(exc, anthropic.NotFoundError):
        return (
            f"Model not found — check DEEPCHECK_MODEL / --model.\n{exc}"
        )
    if isinstance(exc, anthropic.RateLimitError):
        return "Rate limited. Retry, or lower --concurrency."
    if isinstance(exc, anthropic.BadRequestError):
        text = str(exc)
        if "credit balance" in text.lower():
            return (
                "Anthropic rejected the request: the account has no credits.\n"
                "Add credits at https://console.anthropic.com under Plans & Billing.\n"
                "`deepcheck transcribe` still works — it never calls the API."
            )
        return f"Bad request: {exc}"
    if isinstance(exc, anthropic.APIConnectionError):
        return f"Could not reach the Anthropic API: {exc}"
    if isinstance(exc, anthropic.APIStatusError):
        return f"Anthropic API error ({exc.status_code}): {exc}"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
