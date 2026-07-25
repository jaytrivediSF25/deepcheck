# Contributing

## Setup

```bash
make dev        # install with dev dependencies
make upstream   # vendor youtube-deepsummary
make test       # 59 tests, offline
```

## Ground rules

**The test suite stays offline.** No test may call the Anthropic API, YouTube, or
any other network service. Everything network-facing is exercised through fakes.
This keeps CI free, fast, and deterministic — and it means a contributor without
an API key can still run the full suite.

**Verification changes need a stated rationale.** The prompts in `claims.py` and
`verify.py` decide what counts as a claim and what counts as evidence. If you
change one, say in the pull request what behaviour you observed before and after,
on which video. "Seems better" is not reviewable.

**Never invent a source.** Nothing in this project may emit a URL it did not
retrieve. If a claim cannot be tied to a real source, the correct output is
`unverifiable` with the reason attached.

**Match the surrounding code.** Comment density, naming, and structure should be
indistinguishable from the file you are editing.

## Adding a transcript backend

`transcript.py` expects a callable returning a list of `Segment` objects. Add the
new path, register it in `fetch_transcript()`, and return a source label so the
report can record which route produced the text. Provenance is not optional.

## Pull requests

Run `make test` and `make lint` before opening one. CI runs the suite on Linux,
macOS, and Windows against Python 3.10 and 3.12; all six must pass.
