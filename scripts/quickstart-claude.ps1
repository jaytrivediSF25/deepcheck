# One command: set up deepcheck, then open Claude Code in the repo.
. "$PSScriptRoot\_Common.ps1"

Write-Host ""
Write-Host "deepcheck quickstart - Claude Code" -ForegroundColor Cyan
Write-Host ""

Initialize-Environment
Test-Credentials
Start-Agent -Agent 'claude' `
    -InstallHint 'npm install -g @anthropic-ai/claude-code' `
    -Prompt 'This is deepcheck: it transcribes a YouTube video via the vendored youtube-deepsummary project, extracts checkable claims, and verifies each against the live web. Read README.md, then show me how to run a fact-check on a video of my choosing.'
