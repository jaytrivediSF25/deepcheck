"""Core data types for deepcheck.

Everything the pipeline passes around is a plain dataclass so reports, JSON
export and tests all work off the same shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# Ratings are ordered most-to-least severe; report rendering relies on this order.
RATINGS = [
    "false",
    "misleading",
    "mostly_true",
    "true",
    "unverifiable",
    "opinion",
]

RATING_LABELS = {
    "false": "False",
    "misleading": "Misleading",
    "mostly_true": "Mostly true",
    "true": "True",
    "unverifiable": "Unverifiable",
    "opinion": "Opinion / not checkable",
}

CONFIDENCE_LEVELS = ["high", "medium", "low"]

CLAIM_CATEGORIES = [
    "statistic",
    "historical_fact",
    "attribution",
    "policy_claim",
    "scientific_claim",
    "personal_record",
    "prediction",
    "other",
]


@dataclass
class Segment:
    """One transcript cue."""

    start: float
    text: str
    formatted_time: str = ""

    @classmethod
    def from_upstream(cls, entry: Dict[str, Any]) -> "Segment":
        """Build from a youtube-deepsummary transcript entry.

        Upstream emits ``{"time": float, "text": str, "formatted_time": str}``.
        Older youtube-transcript-api rows use ``start``/``duration`` instead, so
        accept either.
        """
        start = entry.get("time", entry.get("start", 0.0))
        return cls(
            start=float(start or 0.0),
            text=(entry.get("text") or "").strip(),
            formatted_time=entry.get("formatted_time") or format_timestamp(start),
        )


@dataclass
class Source:
    title: str
    url: str


@dataclass
class Claim:
    """A single checkable assertion pulled out of the transcript."""

    id: str
    text: str
    quote: str
    category: str = "other"
    checkability: str = "medium"
    start: Optional[float] = None
    formatted_time: str = ""


@dataclass
class Verdict:
    rating: str
    confidence: str
    explanation: str
    correction: str = ""
    sources: List[Source] = field(default_factory=list)
    research_notes: str = ""

    @property
    def label(self) -> str:
        return RATING_LABELS.get(self.rating, self.rating)


@dataclass
class Finding:
    claim: Claim
    verdict: Verdict

    @property
    def rank(self) -> int:
        try:
            return RATINGS.index(self.verdict.rating)
        except ValueError:
            return len(RATINGS)


@dataclass
class Report:
    video_id: str
    video_url: str
    title: str
    checked_at: str
    word_count: int
    findings: List[Finding] = field(default_factory=list)
    model: str = ""
    transcript_source: str = ""

    def sorted_findings(self) -> List[Finding]:
        return sorted(self.findings, key=lambda f: (f.rank, f.claim.start or 0.0))

    def counts(self) -> Dict[str, int]:
        out = {r: 0 for r in RATINGS}
        for f in self.findings:
            out[f.verdict.rating] = out.get(f.verdict.rating, 0) + 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_id": self.video_id,
            "video_url": self.video_url,
            "title": self.title,
            "checked_at": self.checked_at,
            "word_count": self.word_count,
            "model": self.model,
            "transcript_source": self.transcript_source,
            "counts": self.counts(),
            "findings": [
                {"claim": asdict(f.claim), "verdict": asdict(f.verdict)}
                for f in self.sorted_findings()
            ],
        }


def format_timestamp(seconds: Any) -> str:
    """Render seconds as ``H:MM:SS`` (or ``M:SS`` under an hour)."""
    try:
        total = int(float(seconds or 0))
    except (TypeError, ValueError):
        return ""
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
