"""Stage 2 — verify each claim against the live web.

Two calls per claim, deliberately:

1. **Research** with the server-side ``web_search`` tool and no output
   constraint. Search results arrive with citations, and citations cannot be
   combined with ``output_config.format`` — so this call stays unconstrained.
2. **Adjudicate** the research into a strict verdict schema, no tools.

The split also means the verdict is written from evidence already on the page
rather than from the model's recollection.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from .config import Config
from .llm import Client, LLMRefusal, web_search_tool
from .models import CONFIDENCE_LEVELS, RATINGS, Claim, Finding, Source, Verdict

VERDICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "rating": {"type": "string", "enum": RATINGS},
        "confidence": {"type": "string", "enum": CONFIDENCE_LEVELS},
        "explanation": {
            "type": "string",
            "description": (
                "Two to four sentences. State what the evidence shows and how "
                "it compares to the claim. Cite specific figures."
            ),
        },
        "correction": {
            "type": "string",
            "description": (
                "If the claim is false or misleading, the accurate version in "
                "one sentence. Empty string otherwise."
            ),
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["title", "url"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["rating", "confidence", "explanation", "correction", "sources"],
    "additionalProperties": False,
}

RESEARCH_SYSTEM = """\
You are a research assistant for a fact-checking desk. You are given one claim. \
Search the web and report what the best available evidence says.

Method:
- Search for the specific figures, dates, names, and quantities in the claim.
- Prefer primary sources (agency data, official filings, court records, company \
statements, transcripts) over aggregators, and reporting over commentary.
- Look for the strongest evidence AGAINST the claim as well as for it. A claim \
that survives a genuine attempt to refute it is worth more than one you only \
confirmed.
- Note when a claim is directionally right but numerically wrong — that \
distinction matters more than a binary verdict.
- Note when sources disagree, and say who says what.
- If the claim depends on events after your training data, rely on search \
results rather than recollection, and say so.

Report the evidence, the figures, and the URLs you found. Do not render a \
verdict — a separate step does that.\
"""

ADJUDICATE_SYSTEM = """\
You are a fact-checker. Given a claim and a research brief, assign a verdict.

Ratings:
- `true` — accurate as stated.
- `mostly_true` — accurate in substance; minor imprecision that does not change \
the meaning.
- `misleading` — contains real facts arranged to create a false impression, or \
is directionally right but materially wrong on magnitude, or omits context that \
changes the conclusion.
- `false` — contradicted by the evidence.
- `unverifiable` — no adequate public evidence either way. Use this rather than \
guessing.
- `opinion` — a value judgment, prediction, or rhetorical statement that is not \
a factual assertion.

Rules:
- Judge the claim as a listener would understand it, not the most or least \
charitable reading available.
- Numbers matter. If a speaker says 88% and the figure is 40%, that is not \
"mostly true" — the direction being right does not rescue the magnitude.
- `confidence` describes the strength of the evidence, not how strongly you feel.
- Only cite sources that appear in the research brief. Never invent a URL.
- If the brief contains no usable evidence, rate `unverifiable` with low \
confidence.\
"""


def _research(claim: Claim, client: Client, cfg: Config) -> Tuple[str, List[Dict]]:
    response = client.call(
        system=RESEARCH_SYSTEM,
        effort=cfg.verify_effort,
        max_tokens=16000,
        tools=[web_search_tool(cfg.max_searches)],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Claim to research:\n\n{claim.text}\n\n"
                    f"As spoken: “{claim.quote}”"
                ),
            }
        ],
    )
    return client.text_of(response), client.search_sources(response)


def _adjudicate(
    claim: Claim, brief: str, found: List[Dict], client: Client, cfg: Config
) -> Verdict:
    listed = "\n".join(f"- {s['title']}: {s['url']}" for s in found) or "(none)"
    result = client.json_call(
        schema=VERDICT_SCHEMA,
        system=ADJUDICATE_SYSTEM,
        effort=cfg.verify_effort,
        max_tokens=8000,
        messages=[
            {
                "role": "user",
                "content": (
                    f"CLAIM:\n{claim.text}\n\n"
                    f"AS SPOKEN:\n“{claim.quote}”\n\n"
                    f"RESEARCH BRIEF:\n{brief}\n\n"
                    f"SOURCES RETRIEVED:\n{listed}"
                ),
            }
        ],
    )

    sources = [
        Source(title=s.get("title", ""), url=s.get("url", ""))
        for s in result.get("sources", [])
        if s.get("url")
    ]
    if not sources:
        sources = [Source(title=s["title"], url=s["url"]) for s in found]

    return Verdict(
        rating=result.get("rating", "unverifiable"),
        confidence=result.get("confidence", "low"),
        explanation=result.get("explanation", "").strip(),
        correction=result.get("correction", "").strip(),
        sources=sources,
        research_notes=brief,
    )


def verify_claim(claim: Claim, client: Client, cfg: Config) -> Finding:
    try:
        brief, found = _research(claim, client, cfg)
        verdict = _adjudicate(claim, brief, found, client, cfg)
    except LLMRefusal as exc:
        verdict = Verdict(
            rating="unverifiable",
            confidence="low",
            explanation=f"Could not be checked: the request was declined ({exc.category}).",
        )
    except Exception as exc:  # noqa: BLE001 - one bad claim must not kill the run
        verdict = Verdict(
            rating="unverifiable",
            confidence="low",
            explanation=f"Verification failed: {exc}",
        )
    return Finding(claim=claim, verdict=verdict)


def verify_claims(
    claims: List[Claim], client: Client, cfg: Config, on_progress=None
) -> List[Finding]:
    """Verify claims concurrently, preserving input order in the result."""
    findings: List[Finding] = [None] * len(claims)  # type: ignore[list-item]
    done = 0

    with ThreadPoolExecutor(max_workers=max(1, cfg.concurrency)) as pool:
        futures = {
            pool.submit(verify_claim, claim, client, cfg): index
            for index, claim in enumerate(claims)
        }
        for future in as_completed(futures):
            index = futures[future]
            findings[index] = future.result()
            done += 1
            if on_progress:
                on_progress(done, len(claims))

    return findings
