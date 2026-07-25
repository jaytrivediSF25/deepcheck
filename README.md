# deepcheck

Transcribe a YouTube video, pull out every checkable factual claim, and verify each one against the live web.

Transcription is handled by [nickita-khylkouski/youtube-deepsummary](https://github.com/nickita-khylkouski/youtube-deepsummary) — deepcheck imports its `TranscriptExtractor` directly rather than reimplementing extraction. The verification layer on top is this project.

```
YouTube URL
    │
    ├─ youtube-deepsummary  ──►  timestamped transcript      (upstream)
    │      └─ yt-dlp fallback if upstream is unavailable
    │
    ├─ claim extraction     ──►  self-contained claims       (Claude, structured output)
    │
    ├─ verification         ──►  research + verdict          (Claude + server-side web search)
    │
    └─ report               ──►  Markdown / HTML / JSON
```

## Install

```bash
git clone https://github.com/<you>/deepcheck.git
cd deepcheck
pip install -e .

# fetch youtube-deepsummary into vendor/ and install its transcript dependency
./scripts/install_upstream.sh
```

Then set a credential. The SDK resolves `ANTHROPIC_API_KEY`, then `ANTHROPIC_AUTH_TOKEN`, then an `ant auth login` profile — any one works:

```bash
cp .env.example .env   # and fill in ANTHROPIC_API_KEY
# or:
ant auth login
```

## Use

```bash
# transcript only — no API calls, no cost
deepcheck transcribe "https://www.youtube.com/watch?v=VIDEO_ID" -o transcript.txt

# full fact-check
deepcheck check "https://www.youtube.com/watch?v=VIDEO_ID" -f md,html,json -o report

# `check` is the default, so this is equivalent
deepcheck "https://www.youtube.com/watch?v=VIDEO_ID"
```

| Flag | Default | Purpose |
| --- | --- | --- |
| `-o, --out` | `report` | Output path, without extension |
| `-f, --format` | `md` | Any of `md`, `html`, `json`, comma-separated |
| `--max-claims` | `40` | Cap on claims verified. `0` disables the cap |
| `--concurrency` | `4` | Parallel verifications |
| `--max-searches` | `6` | Web searches allowed per claim |
| `--effort` | `high` | `low` … `max`; reasoning depth for verification |
| `--model` | `claude-opus-5` | Model override |
| `--no-fallbacks` | off | Disable the server-side refusal fallback |

Every flag has a `DEEPCHECK_*` environment equivalent — see `.env.example`.

## How verification works

Each claim costs **two** API calls, on purpose.

1. **Research** — Claude runs the server-side `web_search` tool with no output constraint. The prompt asks it to look for evidence *against* the claim as well as for it, and to prefer primary sources.
2. **Adjudicate** — a second call turns that research into a strict verdict schema, with no tools attached.

They are separate because search results carry citations, and citations cannot be combined with `output_config.format` in one request. The split has a second benefit: the verdict is written from evidence already on the page rather than from the model's recollection, which matters for anything after the training cutoff.

Verdicts are `true`, `mostly_true`, `misleading`, `false`, `unverifiable`, or `opinion`. `misleading` is the one that earns its keep — it covers claims that are directionally right but wrong on magnitude, which is where most political numbers land.

## Design notes

**Two transcript paths.** Upstream is primary. If it is missing or fails, deepcheck falls back to `yt-dlp` subtitles and reports which path produced the transcript. During development the fallback earned its place more than once.

**A compatibility shim for upstream.** `youtube-deepsummary` calls `YouTubeTranscriptApi.get_transcript()` and `.list_transcripts()`, classmethods that version 1.2 of `youtube-transcript-api` removed. Upstream pins `==1.1.0`, which is not installable on every Python version, and the last release that kept the classmethods (0.6.2) no longer works against YouTube's current endpoints. `deepcheck/compat.py` re-attaches the two classmethods on top of the modern library so upstream's extractor runs unmodified — no fork, no pinned interpreter. It is a no-op when the methods already exist.

**Claims are anchored to timestamps.** Each extracted claim carries a verbatim quote, which is matched back to a transcript segment — exact substring first, then fuzzy match above a similarity floor, since ASR output and the model's quoting rarely agree character-for-character.

**One bad claim cannot kill a run.** Verification failures and model refusals are caught per claim and recorded as `unverifiable` with the reason attached.

## Limits, stated plainly

- **Verdicts are model-generated.** They are a research aid, not a citation. Every finding ships with its sources; follow them before relying on any single one.
- **Automatic captions are lossy.** Proper nouns get garbled and numbers occasionally do too. The extraction prompt compensates for names but cannot recover what the recognizer dropped.
- **Search coverage is not evenly distributed.** Claims about recent, well-covered events verify well. Claims about obscure or paywalled material return `unverifiable` more often than they should.
- **Cost scales with claims**, not video length — two calls per claim, plus one per transcript chunk for extraction.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The suite covers URL parsing, VTT parsing and rolling-window collapse, chunking, timestamp anchoring, claim prioritization, the compat shim, report rendering in all three formats, HTML escaping, and CLI argument routing. It does not call the API.

## Licence

MIT. `youtube-deepsummary` is a separate project under its own licence; this repository vendors it at install time rather than redistributing it.
