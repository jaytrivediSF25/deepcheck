# Shared setup for the Windows quickstart scripts. Dot-sourced, not run directly.

$ErrorActionPreference = 'Stop'

$script:Root = Split-Path -Parent $PSScriptRoot
Set-Location $script:Root

function Write-Step { param($Text) Write-Host $Text -ForegroundColor White }
function Write-Ok   { param($Text) Write-Host "  [ok] $Text" -ForegroundColor Green }
function Write-Warn { param($Text) Write-Host "  [!]  $Text" -ForegroundColor Yellow }
function Write-Dim  { param($Text) Write-Host "       $Text" -ForegroundColor DarkGray }

function Find-Python {
    foreach ($candidate in @('python', 'python3', 'py')) {
        $exe = Get-Command $candidate -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        # `py` and Store aliases can exist but not run; check the version too.
        & $candidate -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    throw "deepcheck needs Python 3.10 or newer on PATH. Install it from https://python.org/downloads (tick 'Add python.exe to PATH')."
}

function Initialize-Environment {
    Write-Step "1/4  Python environment"
    $py = Find-Python
    Write-Ok (& $py --version 2>&1)

    if (-not (Test-Path '.venv')) {
        & $py -m venv .venv
        Write-Ok "created .venv"
    } else {
        Write-Ok ".venv already present"
    }

    $script:VenvPy = Join-Path $script:Root '.venv\Scripts\python.exe'
    if (-not (Test-Path $script:VenvPy)) {
        throw "Virtual environment looks incomplete: $script:VenvPy not found."
    }

    Write-Step "2/4  Dependencies"
    & $script:VenvPy -m pip install --quiet --upgrade pip
    & $script:VenvPy -m pip install --quiet -e .
    Write-Ok "deepcheck installed (editable)"

    Write-Step "3/4  Upstream transcriber"
    if (Test-Path 'vendor\youtube-deepsummary\.git') {
        Write-Ok "youtube-deepsummary already vendored"
    } else {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            throw "git is required. Install it from https://git-scm.com/download/win"
        }
        git clone --depth 1 https://github.com/nickita-khylkouski/youtube-deepsummary.git `
            vendor\youtube-deepsummary 2>&1 | Out-Null
        Write-Ok "cloned youtube-deepsummary"
    }
    & $script:VenvPy -m pip install --quiet "youtube-transcript-api<1.2"
    Write-Ok "transcript backend ready"
}

function Test-Credentials {
    Write-Step "4/4  Credentials"
    if ($env:ANTHROPIC_API_KEY) {
        Write-Ok "ANTHROPIC_API_KEY is set"
        return
    }
    if ((Test-Path '.env') -and (Select-String -Path '.env' -Pattern '^ANTHROPIC_API_KEY=.+' -Quiet)) {
        Write-Ok "ANTHROPIC_API_KEY found in .env"
        return
    }
    if (Get-Command ant -ErrorAction SilentlyContinue) {
        ant auth status *> $null
        if ($LASTEXITCODE -eq 0) { Write-Ok "authenticated via an ant profile"; return }
    }
    Write-Warn "no Anthropic credential found"
    Write-Dim '$env:ANTHROPIC_API_KEY = "sk-ant-..."   (or run: ant auth login)'
    Write-Dim "'deepcheck transcribe' works without one."
}

function Start-Agent {
    param($Agent, $InstallHint, $Prompt)
    Write-Host ""
    if (-not (Get-Command $Agent -ErrorAction SilentlyContinue)) {
        Write-Warn "'$Agent' is not on PATH"
        Write-Dim "install it with: $InstallHint"
        Write-Dim "Setup is done - rerun this script once $Agent is installed."
        return
    }
    Write-Step "Opening $Agent in $script:Root"
    Write-Host ""
    & $Agent $Prompt
}
