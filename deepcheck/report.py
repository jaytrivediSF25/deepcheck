"""Rendering: Markdown, JSON, and a self-contained HTML page."""

from __future__ import annotations

import html
import json
from typing import List

from .models import RATING_LABELS, RATINGS, Finding, Report

# Black / white / light blue, matching the reference report styling.
_ACCENT = "#1573b8"
_ACCENT_DARK = "#7cc4f5"


def to_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------


def to_markdown(report: Report) -> str:
    lines: List[str] = []
    add = lines.append

    add(f"# Fact-check: {report.title or report.video_id}")
    add("")
    add(f"**Source:** [{report.video_url}]({report.video_url})")
    add(f"**Checked:** {report.checked_at}")
    add(f"**Transcript:** {report.word_count:,} words (via {report.transcript_source})")
    add(f"**Model:** {report.model}")
    add("")

    counts = report.counts()
    add("| Verdict | Claims |")
    add("| --- | ---: |")
    for rating in RATINGS:
        if counts.get(rating):
            add(f"| {RATING_LABELS[rating]} | {counts[rating]} |")
    add(f"| **Total** | **{len(report.findings)}** |")
    add("")

    for rating in RATINGS:
        group = [f for f in report.sorted_findings() if f.verdict.rating == rating]
        if not group:
            continue
        add("---")
        add("")
        add(f"## {RATING_LABELS[rating]}")
        add("")
        for finding in group:
            add(_markdown_finding(finding))

    add("---")
    add("")
    add(
        "*Verdicts are model-generated from live web search. "
        "Follow the sources before relying on any single finding.*"
    )
    return "\n".join(lines)


def _markdown_finding(finding: Finding) -> str:
    claim, verdict = finding.claim, finding.verdict
    stamp = f" `[{claim.formatted_time}]`" if claim.formatted_time else ""

    parts = [f"### {claim.text}{stamp}", ""]
    if claim.quote:
        parts += [f"> {claim.quote}", ""]
    parts += [verdict.explanation, ""]
    if verdict.correction:
        parts += [f"**Correction:** {verdict.correction}", ""]
    parts.append(f"*Confidence: {verdict.confidence}*")
    parts.append("")
    if verdict.sources:
        parts.append("Sources:")
        for source in verdict.sources:
            title = source.title or source.url
            parts.append(f"- [{title}]({source.url})")
        parts.append("")
    return "\n".join(parts)


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------


def to_html(report: Report) -> str:
    e = html.escape
    counts = report.counts()

    sections: List[str] = []
    for rating in RATINGS:
        group = [f for f in report.sorted_findings() if f.verdict.rating == rating]
        if not group:
            continue
        items = "\n".join(_html_finding(f) for f in group)
        sections.append(
            f'<section id="{rating}">\n'
            f'<h2><span class="chip">{e(RATING_LABELS[rating])}</span>'
            f'<span class="count">{len(group)}</span></h2>\n{items}\n</section>'
        )

    nav = " ".join(
        f'<a href="#{r}">{e(RATING_LABELS[r])} ({counts[r]})</a>'
        for r in RATINGS
        if counts.get(r)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fact-check: {e(report.title or report.video_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <p class="kicker">Fact-check</p>
  <h1>{e(report.title or report.video_id)}</h1>
  <dl class="meta">
    <dt>Source</dt><dd><a href="{e(report.video_url)}">{e(report.video_url)}</a></dd>
    <dt>Checked</dt><dd>{e(report.checked_at)}</dd>
    <dt>Transcript</dt><dd>{report.word_count:,} words &middot; {e(report.transcript_source)}</dd>
    <dt>Claims</dt><dd>{len(report.findings)}</dd>
  </dl>
  <nav>{nav}</nav>
</header>
<main>
{chr(10).join(sections)}
</main>
<footer>
  <p>Verdicts are model-generated ({e(report.model)}) from live web search.
     Follow the sources before relying on any single finding.</p>
</footer>
</body>
</html>
"""


def _html_finding(finding: Finding) -> str:
    e = html.escape
    claim, verdict = finding.claim, finding.verdict

    stamp = (
        f'<span class="stamp">{e(claim.formatted_time)}</span>'
        if claim.formatted_time
        else ""
    )
    quote = f"<blockquote>{e(claim.quote)}</blockquote>" if claim.quote else ""
    correction = (
        f'<p class="correction"><strong>Correction.</strong> {e(verdict.correction)}</p>'
        if verdict.correction
        else ""
    )
    sources = ""
    if verdict.sources:
        links = "\n".join(
            f'<li><a href="{e(s.url)}">{e(s.title or s.url)}</a></li>'
            for s in verdict.sources
        )
        sources = f'<div class="sources"><h4>Sources</h4><ul>{links}</ul></div>'

    return f"""<article>
  <h3>{e(claim.text)} {stamp}</h3>
  {quote}
  <p>{e(verdict.explanation)}</p>
  {correction}
  {sources}
  <p class="conf">Confidence: {e(verdict.confidence)}</p>
</article>"""


_CSS = f"""
:root {{
  --bg: #ffffff; --fg: #111111; --muted: #5b5b5b;
  --rule: #e2e2e2; --blue: {_ACCENT}; --blue-soft: #eaf4fb;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0e0e0f; --fg: #f2f2f2; --muted: #a2a2a2;
    --rule: #2a2a2c; --blue: {_ACCENT_DARK}; --blue-soft: #12222e;
  }}
}}
:root[data-theme="light"] {{
  --bg: #ffffff; --fg: #111111; --muted: #5b5b5b;
  --rule: #e2e2e2; --blue: {_ACCENT}; --blue-soft: #eaf4fb;
}}
:root[data-theme="dark"] {{
  --bg: #0e0e0f; --fg: #f2f2f2; --muted: #a2a2a2;
  --rule: #2a2a2c; --blue: {_ACCENT_DARK}; --blue-soft: #12222e;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 3rem 1.25rem 5rem; background: var(--bg); color: var(--fg);
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  overflow-wrap: break-word;
}}
header, main, footer {{ max-width: 43rem; margin: 0 auto; }}
.kicker {{
  margin: 0 0 .5rem; color: var(--blue); font-size: .75rem;
  letter-spacing: .14em; text-transform: uppercase; font-weight: 700;
}}
h1 {{ margin: 0 0 1.5rem; font-size: 2rem; line-height: 1.2; letter-spacing: -.02em; }}
.meta {{
  display: grid; grid-template-columns: 7rem 1fr; gap: .35rem 1rem;
  margin: 0 0 1.75rem; padding-bottom: 1.75rem; border-bottom: 3px solid var(--blue);
  font-size: .9rem;
}}
.meta dt {{ color: var(--muted); }}
.meta dd {{ margin: 0; }}
nav {{ display: flex; flex-wrap: wrap; gap: .5rem 1.25rem; font-size: .85rem; }}
a {{ color: var(--blue); }}
h2 {{
  display: flex; align-items: center; gap: .75rem; margin: 3.5rem 0 1.5rem;
  padding-top: 1.25rem; border-top: 2px solid var(--rule); font-size: 1rem;
}}
.chip {{
  background: var(--blue); color: var(--bg); padding: .3rem .7rem;
  border-radius: 3px; font-size: .75rem; letter-spacing: .1em;
  text-transform: uppercase; font-weight: 700;
}}
.count {{ color: var(--muted); font-weight: 400; }}
article {{ margin: 0 0 2.5rem; padding-left: 1rem; border-left: 3px solid var(--rule); }}
h3 {{ margin: 0 0 .6rem; font-size: 1.1rem; line-height: 1.35; }}
.stamp {{
  display: inline-block; color: var(--blue); font-size: .75rem;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 400;
}}
blockquote {{
  margin: 0 0 .9rem; padding: .5rem .9rem; background: var(--blue-soft);
  color: var(--muted); font-style: italic; font-size: .92rem;
}}
p {{ margin: 0 0 .8rem; }}
.correction {{ border-left: 3px solid var(--blue); padding-left: .8rem; }}
.sources h4 {{
  margin: 1rem 0 .4rem; font-size: .72rem; letter-spacing: .1em;
  text-transform: uppercase; color: var(--muted);
}}
.sources ul {{ margin: 0; padding-left: 1.1rem; font-size: .88rem; }}
.sources li {{ margin-bottom: .25rem; overflow-wrap: anywhere; }}
.conf {{ margin-top: .9rem; color: var(--muted); font-size: .8rem; }}
footer {{
  margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid var(--rule);
  color: var(--muted); font-size: .85rem;
}}
@media (max-width: 32rem) {{
  body {{ padding-top: 2rem; }}
  h1 {{ font-size: 1.6rem; }}
  .meta {{ grid-template-columns: 1fr; gap: 0 0; }}
  .meta dt {{ margin-top: .6rem; font-size: .75rem; text-transform: uppercase; }}
}}
"""
