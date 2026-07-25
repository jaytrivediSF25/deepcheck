# Fetch nickita-khylkouski/youtube-deepsummary into vendor/ and install the one
# dependency deepcheck needs from it.
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$dest = if ($env:DEEPCHECK_UPSTREAM_PATH) { $env:DEEPCHECK_UPSTREAM_PATH }
        else { Join-Path $root 'vendor\youtube-deepsummary' }

if (Test-Path (Join-Path $dest '.git')) {
    Write-Host "Updating $dest"
    git -C $dest pull --ff-only
} else {
    Write-Host "Cloning youtube-deepsummary into $dest"
    git clone --depth 1 https://github.com/nickita-khylkouski/youtube-deepsummary.git $dest
}

# Upstream calls the classmethod API (YouTubeTranscriptApi.get_transcript /
# .list_transcripts). youtube-transcript-api 1.2+ removed those, so pin below it.
python -m pip install "youtube-transcript-api<1.2"

Write-Host ""
Write-Host "Done. youtube-deepsummary is at $dest"
