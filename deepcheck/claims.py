"""Stage 1 — pull checkable claims out of the transcript.

The transcript is chunked so long videos stay well inside a single request, and
each chunk is extracted independently. Claims are then anchored back to a
timestamp by locating their supporting quote in the segment list.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .config import Config
from .models import CLAIM_CATEGORIES, Claim, Segment, format_timestamp
from .security import UNTRUSTED_NOTICE, wrap_untrusted

if TYPE_CHECKING:  # keeps chunking/anchoring importable without the SDK installed
    from .llm import Client

CLAIM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "The claim restated as a single self-contained "
                            "sentence, with pronouns and references resolved so "
                            "it can be checked without the surrounding context."
                        ),
                    },
                    "quote": {
                        "type": "string",
                        "description": "Verbatim span from the transcript that carries the claim.",
                    },
                    "category": {"type": "string", "enum": CLAIM_CATEGORIES},
                    "checkability": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": (
                            "high = specific and verifiable against public "
                            "record; low = vague, subjective, or predictive."
                        ),
                    },
                },
                "required": ["text", "quote", "category", "checkability"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}

EXTRACT_SYSTEM = """\
You extract checkable factual claims from spoken-word transcripts for a \
fact-checking pipeline.

A claim qualifies if a diligent researcher could confirm or refute it against \
public record: statistics, dated events, quantities, attributions ("X said Y"), \
records and rankings, causal assertions about policy, scientific assertions.

Do NOT extract:
- opinions, value judgments, or aesthetic preferences
- jokes, hyperbole, and sarcasm that no listener would take literally
- pure predictions about the future with no present-tense factual content
- statements about the speaker's own intentions or feelings
- pleasantries, greetings, and procedural remarks

Rules:
- Restate each claim so it stands alone. Resolve every pronoun and deictic \
reference ("last year", "over there", "he") using the surrounding transcript.
- Preserve the speaker's numbers exactly as spoken. Do not round or correct them.
- `quote` must be a verbatim substring of the transcript you were given.
- The transcript comes from automatic speech recognition. Proper nouns are often \
garbled. Infer the intended name and use the correct spelling in `text`, but keep \
`quote` verbatim.
- Prefer the specific over the general. "Crime fell 88%" beats "crime fell".
- If a passage contains no checkable claims, return an empty list. Do not \
manufacture claims to fill space.

""" + UNTRUSTED_NOTICE


def chunk_segments(
    segments: List[Segment], chunk_words: int
) -> List[List[Segment]]:
    """Split segments into runs of roughly ``chunk_words`` words."""
    chunks: List[List[Segment]] = []
    current: List[Segment] = []
    count = 0

    for segment in segments:
        words = len(segment.text.split())
        if current and count + words > chunk_words:
            chunks.append(current)
            current = []
            count = 0
        current.append(segment)
        count += words

    if current:
        chunks.append(current)
    return chunks


def _render_chunk(chunk: List[Segment]) -> str:
    return "\n".join(
        f"[{s.formatted_time or format_timestamp(s.start)}] {s.text}" for s in chunk
    )


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def anchor_claim(quote: str, chunk: List[Segment]) -> Optional[Segment]:
    """Find the segment a quote came from.

    Exact substring first; if ASR drift or the model's paraphrasing breaks that,
    fall back to the best fuzzy match above a similarity floor.
    """
    target = _normalize(quote)
    if not target:
        return None

    for segment in chunk:
        if target in _normalize(segment.text):
            return segment

    head = " ".join(target.split()[:8])
    best: Optional[Segment] = None
    best_score = 0.0
    for segment in chunk:
        score = SequenceMatcher(None, head, _normalize(segment.text)).ratio()
        if score > best_score:
            best_score, best = score, segment

    return best if best_score >= 0.45 else None


def extract_claims(
    segments: List[Segment],
    client: "Client",
    cfg: Config,
    on_progress=None,
) -> List[Claim]:
    """Run extraction over every chunk and return anchored, deduped claims."""
    chunks = chunk_segments(segments, cfg.chunk_words)
    claims: List[Claim] = []
    seen: set[str] = set()

    for index, chunk in enumerate(chunks, start=1):
        if on_progress:
            on_progress(index, len(chunks))

        body = _render_chunk(chunk)
        result = client.json_call(
            schema=CLAIM_SCHEMA,
            system=EXTRACT_SYSTEM,
            effort=cfg.extract_effort,
            max_tokens=16000,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Transcript excerpt {index} of {len(chunks)}. "
                        "Extract the checkable factual claims.\n\n"
                        + wrap_untrusted("transcript", body)
                    ),
                }
            ],
        )

        for item in result.get("claims", []):
            text = (item.get("text") or "").strip()
            if not text:
                continue

            key = _normalize(text)[:120]
            if key in seen:
                continue
            seen.add(key)

            quote = (item.get("quote") or "").strip()
            anchor = anchor_claim(quote, chunk)
            claims.append(
                Claim(
                    id=f"c{len(claims) + 1:03d}",
                    text=text,
                    quote=quote,
                    category=item.get("category", "other"),
                    checkability=item.get("checkability", "medium"),
                    start=anchor.start if anchor else None,
                    formatted_time=anchor.formatted_time if anchor else "",
                )
            )

    return prioritize(claims, cfg.max_claims)


def prioritize(claims: List[Claim], limit: int) -> List[Claim]:
    """Trim to ``limit``, keeping the most checkable claims and original order."""
    if limit <= 0 or len(claims) <= limit:
        return claims

    rank = {"high": 0, "medium": 1, "low": 2}
    ordered = sorted(
        enumerate(claims),
        key=lambda pair: (rank.get(pair[1].checkability, 3), pair[0]),
    )
    kept = sorted(ordered[:limit], key=lambda pair: pair[0])
    return [claim for _, claim in kept]
