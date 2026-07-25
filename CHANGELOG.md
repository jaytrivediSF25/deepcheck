# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-07-25

First working release.

### Added
- Transcript acquisition on top of [youtube-deepsummary](https://github.com/nickita-khylkouski/youtube-deepsummary),
  importing its `TranscriptExtractor` directly, with a `yt-dlp` subtitle fallback.
  The report records which route produced the text.
- `compat.py` — re-attaches `get_transcript()` / `list_transcripts()` on top of
  `youtube-transcript-api` 1.2+, so upstream's extractor runs unmodified against
  a library version that removed them.
- Claim isolation with structured output: chunking, standalone rewriting,
  verbatim-quote timestamp anchoring, and checkability-based prioritization.
- Two-stage verification — adversarial web search, then adjudication under a
  strict verdict schema with no tools attached.
- Six-class verdict taxonomy including `misleading`, for claims that are
  directionally right and materially wrong.
- Markdown, JSON, and self-contained HTML reports.
- Quickstart launchers for Claude Code and Codex on macOS, Linux, and Windows.
- Docker image, Makefile, and cross-platform CI.
- 59 offline tests.

### Security
- `security.py` — trust boundaries in one place: URL scheme allow-listing,
  video-ID validation, control/bidi character stripping, prompt fencing.
- Citation admissibility: a source is kept only if the search tool actually
  retrieved that URL, so a fabricated or injected citation cannot reach a report.
- Report renderers validate every URL before it reaches an `href`; unsupported
  schemes render as inert text rather than being silently dropped.
- Prompt-injection boundary notice on all three model stages.
- CI: pip-audit, CodeQL, Bandit, and grep guards against `shell=True` and raw
  URL interpolation.
- See [SECURITY.md](SECURITY.md).

### Known limits
- Verdicts are model-generated and published with their sources; they are a
  research aid, not a citation.
- Automatic captions garble proper nouns. The extraction prompt compensates for
  names but cannot recover what the recognizer dropped.
- Obscure or paywalled material returns `unverifiable` more often than it should.
