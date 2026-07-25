#!/usr/bin/env bash
# One command: set up deepcheck, then open Claude Code in the repo.
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

printf '\n\033[1mdeepcheck quickstart — Claude Code\033[0m\n\n'
setup_env
check_credentials
launch claude \
  "npm install -g @anthropic-ai/claude-code" \
  "This is deepcheck: it transcribes a YouTube video via the vendored youtube-deepsummary project, extracts checkable claims, and verifies each against the live web. Read README.md, then show me how to run a fact-check on a video of my choosing."
