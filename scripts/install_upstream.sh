#!/usr/bin/env bash
# Fetch nickita-khylkouski/youtube-deepsummary into vendor/ and install the one
# dependency deepcheck needs from it (youtube-transcript-api).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${DEEPCHECK_UPSTREAM_PATH:-$ROOT/vendor/youtube-deepsummary}"
REPO="https://github.com/nickita-khylkouski/youtube-deepsummary.git"

if [ -d "$DEST/.git" ]; then
  echo "Updating $DEST"
  git -C "$DEST" pull --ff-only
else
  echo "Cloning youtube-deepsummary into $DEST"
  git clone --depth 1 "$REPO" "$DEST"
fi

# deepcheck imports only src/transcript_extractor.py, which needs just this.
# Upstream calls the classmethod API (YouTubeTranscriptApi.get_transcript /
# .list_transcripts). youtube-transcript-api 1.2+ removed those in favour of an
# instance API, so pin below it. Install upstream's full requirements.txt only
# if you also want to run its Flask app.
python3 -m pip install "youtube-transcript-api<1.2"

echo
echo "Done. youtube-deepsummary is at $DEST"
