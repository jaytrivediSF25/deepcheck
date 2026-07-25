"""Runtime configuration, read from the environment with sane defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:  # optional; the upstream project ships it, we don't require it
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a convenience, not a dependency
    pass


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UPSTREAM = REPO_ROOT / "vendor" / "youtube-deepsummary"


@dataclass
class Config:
    """Everything tunable in one place."""

    # Anthropic. The SDK resolves credentials itself (ANTHROPIC_API_KEY, then
    # ANTHROPIC_AUTH_TOKEN, then an `ant auth login` profile), so an unset
    # api_key here is not an error.
    api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    model: str = os.getenv("DEEPCHECK_MODEL", "claude-opus-5")
    extract_effort: str = os.getenv("DEEPCHECK_EXTRACT_EFFORT", "medium")
    verify_effort: str = os.getenv("DEEPCHECK_VERIFY_EFFORT", "high")

    # Where youtube-deepsummary lives. We import its TranscriptExtractor from here.
    upstream_path: Path = Path(
        os.getenv("DEEPCHECK_UPSTREAM_PATH", str(DEFAULT_UPSTREAM))
    )

    # Pipeline shape.
    chunk_words: int = int(os.getenv("DEEPCHECK_CHUNK_WORDS", 1800))
    max_claims: int = int(os.getenv("DEEPCHECK_MAX_CLAIMS", 40))
    concurrency: int = int(os.getenv("DEEPCHECK_CONCURRENCY", 4))
    max_searches: int = int(os.getenv("DEEPCHECK_MAX_SEARCHES", 6))

    # Server-side refusal fallback. Claude Opus 5 runs safety classifiers that can
    # decline a request; `fallbacks="default"` re-runs it on Anthropic's
    # recommended fallback model instead of returning the refusal.
    use_fallbacks: bool = os.getenv("DEEPCHECK_FALLBACKS", "1") != "0"

    def upstream_available(self) -> bool:
        return (self.upstream_path / "src" / "transcript_extractor.py").is_file()


def load_config(**overrides) -> Config:
    cfg = Config()
    for key, value in overrides.items():
        if value is not None and hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg
