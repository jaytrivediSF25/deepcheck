"""Transcript acquisition.

Primary path is nickita-khylkouski/youtube-deepsummary: we import its
``TranscriptExtractor`` directly rather than reimplementing extraction. That
module only depends on ``youtube_transcript_api`` — no Flask, no Supabase — so
importing it is cheap and has no side effects.

If upstream isn't checked out (or its extraction fails), we fall back to
``yt-dlp`` subtitles so the tool still works standalone.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .config import Config
from .models import Segment, format_timestamp
from .security import MAX_INPUT_LENGTH, is_video_id, strip_control


class TranscriptError(RuntimeError):
    pass


def parse_video_id(url_or_id: str) -> str:
    """Accept a bare ID, a watch URL, youtu.be, shorts, or embed URL.

    The result is the only user-controlled component of the URLs handed to
    yt-dlp, so it is validated against a strict character class rather than
    merely extracted.
    """
    value = strip_control(url_or_id or "")
    if len(value) > MAX_INPUT_LENGTH:
        raise TranscriptError("Input is implausibly long for a YouTube URL")
    if is_video_id(value):
        return value

    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"/shorts/([A-Za-z0-9_-]{11})",
        r"/embed/([A-Za-z0-9_-]{11})",
        r"/live/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match and is_video_id(match.group(1)):
            return match.group(1)

    raise TranscriptError(f"Could not find a YouTube video ID in {url_or_id!r}")


def watch_url(video_id: str) -> str:
    """Build the canonical watch URL, re-validating the ID first.

    Every URL handed to yt-dlp is built here, so this is the choke point worth
    enforcing at. Interpolating an unvalidated ID would let a caller steer the
    fetch somewhere else entirely — `abc&list=...` appends a parameter,
    `x/../../other` walks to a different path — which turns a video fetch into
    a request for an arbitrary URL. Callers inside the CLI already run
    `parse_video_id`; library callers may not, so the check lives here rather
    than depending on the call site.
    """
    if not is_video_id(video_id):
        raise TranscriptError(f"Refusing to build a URL from invalid video ID {video_id!r}")
    return f"https://www.youtube.com/watch?v={video_id}"


# --------------------------------------------------------------------------
# Upstream (youtube-deepsummary)
# --------------------------------------------------------------------------


def _import_upstream(cfg: Config):
    """Put upstream on sys.path and return its module-level extract_transcript."""
    if not cfg.upstream_available():
        raise TranscriptError(
            f"youtube-deepsummary not found at {cfg.upstream_path}.\n"
            "Run scripts/install_upstream.sh, or set DEEPCHECK_UPSTREAM_PATH "
            "to an existing checkout."
        )

    path = str(cfg.upstream_path)
    if path not in sys.path:
        sys.path.insert(0, path)

    # Upstream targets the pre-1.2 classmethod API; re-attach it if needed.
    from . import compat

    compat.install()

    try:
        from src.transcript_extractor import extract_transcript  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on local install
        raise TranscriptError(
            "Found youtube-deepsummary but could not import "
            f"src.transcript_extractor ({exc}). Install its dependencies:\n"
            f"    pip install -r {cfg.upstream_path / 'requirements.txt'}"
        ) from exc

    return extract_transcript


def fetch_via_upstream(video_id: str, cfg: Config) -> List[Segment]:
    # Upstream builds its own request from this ID; validate before handing it
    # across the boundary rather than inheriting whatever it does with it.
    if not is_video_id(video_id):
        raise TranscriptError(f"Invalid video ID {video_id!r}")
    extract = _import_upstream(cfg)
    raw = extract(video_id)
    if not raw:
        raise TranscriptError("Upstream returned an empty transcript")
    return [Segment.from_upstream(entry) for entry in raw]


# --------------------------------------------------------------------------
# Fallback (yt-dlp subtitles)
# --------------------------------------------------------------------------

_TS_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


def _ytdlp_binary() -> List[str]:
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    if shutil.which("uvx"):
        return ["uvx", "yt-dlp"]
    raise TranscriptError(
        "yt-dlp fallback needs `yt-dlp` or `uvx` on PATH. "
        "Install with: pip install yt-dlp"
    )


def fetch_via_ytdlp(video_id: str) -> List[Segment]:
    binary = _ytdlp_binary()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "sub"
        cmd = binary + [
            "--skip-download",
            "--write-sub",
            "--write-auto-sub",
            "--sub-lang",
            "en.*",
            "--sub-format",
            "vtt",
            "-o",
            str(out) + ".%(ext)s",
            watch_url(video_id),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        vtts = sorted(Path(tmp).glob("*.vtt"), key=lambda p: len(p.name))
        if not vtts:
            raise TranscriptError(
                f"yt-dlp produced no subtitles for {video_id}. "
                f"stderr: {proc.stderr.strip()[:400]}"
            )
        return parse_vtt(vtts[0].read_text(encoding="utf-8", errors="replace"))


def parse_vtt(raw: str) -> List[Segment]:
    """Parse WebVTT into segments, collapsing YouTube's rolling-window repeats."""
    segments: List[Segment] = []
    pending_start: Optional[float] = None

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue

        match = _TS_RE.search(line)
        if match:
            h, m, s, ms = (int(match.group(i)) for i in range(1, 5))
            pending_start = h * 3600 + m * 60 + s + ms / 1000.0
            continue

        text = _TAG_RE.sub("", line)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue

        # Auto-captions repeat the previous cue as a scrolling window.
        if segments:
            prev = segments[-1].text
            if text == prev or prev.endswith(text):
                continue
            if text.startswith(prev):
                segments[-1].text = text
                continue

        start = pending_start if pending_start is not None else 0.0
        segments.append(
            Segment(start=start, text=text, formatted_time=format_timestamp(start))
        )

    if not segments:
        raise TranscriptError("VTT parsed to zero segments")
    return segments


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def fetch_transcript(video_id: str, cfg: Config) -> Tuple[List[Segment], str]:
    """Return (segments, source) where source is 'upstream' or 'yt-dlp'."""
    errors = []
    try:
        return fetch_via_upstream(video_id, cfg), "youtube-deepsummary"
    except Exception as exc:  # noqa: BLE001 - any upstream failure should fall back
        errors.append(f"upstream: {exc}")

    try:
        return fetch_via_ytdlp(video_id), "yt-dlp"
    except Exception as exc:  # noqa: BLE001
        errors.append(f"yt-dlp: {exc}")

    raise TranscriptError(
        "Could not fetch a transcript.\n  " + "\n  ".join(errors)
    )


def fetch_metadata(video_id: str) -> dict:
    """Best-effort title/channel/duration via yt-dlp. Never fatal."""
    try:
        binary = _ytdlp_binary()
    except TranscriptError:
        return {}
    try:
        proc = subprocess.run(
            binary + ["--skip-download", "--dump-single-json", watch_url(video_id)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            return {}
        data = json.loads(proc.stdout)
        return {
            "title": data.get("title", ""),
            "channel": data.get("channel", ""),
            "duration": data.get("duration_string", ""),
        }
    except Exception:  # noqa: BLE001 - metadata is decoration
        return {}


def to_text(segments: List[Segment]) -> str:
    return re.sub(r"\s+", " ", " ".join(s.text for s in segments)).strip()


def word_count(segments: List[Segment]) -> int:
    return len(to_text(segments).split())
