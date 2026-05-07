#Requires -Version 5.1
<#
.SYNOPSIS
    agent-mcp — installation script for Windows (PowerShell 5.1+).

.DESCRIPTION
    Installs agent-mcp, creates a virtual environment, sets up the
    platform data directory (%LOCALAPPDATA%\agent-mcp\), and writes
    the initial .env configuration file.

.PARAMETER NoVenv
    Skip virtual environment creation and use the current Python.

.PARAMETER VenvDir
    Path for the virtual environment. Default: .venv

.PARAMETER DataDir
    Override the platform data directory (default: %LOCALAPPDATA%\agent-mcp).

.PARAMETER NoFrontend
    Skip Node.js / pnpm frontend dependency check.

.PARAMETER Dev
    Install in editable mode (pip install -e .).

.EXAMPLE
    .\install.ps1
    .\install.ps1 -Dev
    .\install.ps1 -VenvDir C:\tools\agent-venv -DataDir D:\AgentData
#>
[CmdletBinding()]
param(
    [switch]$NoVenv,
    [string]$VenvDir    = ".venv",
    [string]$DataDir    = "",
    [switch]$NoFrontend,
    [switch]$Dev
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── colour helpers ────────────────────────────────────────────────────────────
function Write-Info    { param($m) Write-Host "  " -NoNewline; Write-Host "●" -ForegroundColor Cyan -NoNewline; Write-Host " $m" }
function Write-Success { param($m) Write-Host "  " -NoNewline; Write-Host "✔" -ForegroundColor Green -NoNewline; Write-Host " $m" }
function Write-Warn    { param($m) Write-Host "  " -NoNewline; Write-Host "⚠" -ForegroundColor Yellow -NoNewline; Write-Host " $m" }
function Write-Err     { param($m) Write-Host "  " -NoNewline; Write-Host "✖" -ForegroundColor Red -NoNewline; Write-Host " $m" >&2 }
function Write-Header  { param($m) Write-Host; Write-Host "══ $m ══" -ForegroundColor Cyan; Write-Host }
function Fail          { param($m) Write-Err $m; exit 1 }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ── banner ────────────────────────────────────────────────────────────────────
Write-Host
Write-Host "  ╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║         agent-mcp  installer         ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host

# ── Python check ─────────────────────────────────────────────────────────────
Write-Header "Checking Python"

$PythonExe = $null
$Candidates = @("python3.13","python3.12","python3.11","python3","python","py")
foreach ($cand in $Candidates) {
    try {
        $ver = & $cand -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        if ($ver -match '^(\d+)\.(\d+)') {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $PythonExe = $cand; $PythonVer = $ver; break
            }
        }
    } catch { continue }
}

if (-not $PythonExe) {
    Fail "Python 3.11 or newer is required but was not found.`n  Download from https://python.org/downloads"
}
Write-Success "Python $PythonVer  ($PythonExe)"

# ── virtual environment ───────────────────────────────────────────────────────
Write-Header "Virtual environment"

Set-Location $ScriptDir

if (-not $NoVenv) {
    $VenvPath = Join-Path $ScriptDir $VenvDir
    if (Test-Path $VenvPath) {
        Write-Info "Existing virtual environment found at $VenvDir"
    } else {
        Write-Info "Creating virtual environment at $VenvDir"
        & $PythonExe -m venv $VenvPath
        if ($LASTEXITCODE -ne 0) { Fail "Failed to create virtual environment." }
    }
    $PythonExe = Join-Path $VenvPath "Scripts\python.exe"
    Write-Success "Virtual environment ready"
} else {
    Write-Warn "--NoVenv: using current Python ($PythonExe)"
}

# ── pip upgrade ───────────────────────────────────────────────────────────────
Write-Info "Upgrading pip..."
& $PythonExe -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed." }

# ── package install ───────────────────────────────────────────────────────────
Write-Header "Installing agent-mcp"

if ($Dev) {
    Write-Info "Installing in editable/development mode..."
    & $PythonExe -m pip install -e ".[graph-watch]"
} else {
    Write-Info "Installing package..."
    & $PythonExe -m pip install ".[graph-watch]"
}
if ($LASTEXITCODE -ne 0) { Fail "Package installation failed." }
Write-Success "Package installed"

# ── data directory setup ──────────────────────────────────────────────────────
Write-Header "Setting up data directory"

$ResolvedDataDir = if ($DataDir) {
    [System.IO.Path]::GetFullPath($DataDir)
} else {
    $localAppData = $env:LOCALAPPDATA
    if (-not $localAppData) { $localAppData = Join-Path $env:USERPROFILE "AppData\Local" }
    Join-Path $localAppData "agent-mcp"
}

# Honour AGENT_DATA_DIR env var if set (and no explicit CLI override)
if (-not $DataDir -and $env:AGENT_DATA_DIR) {
    $ResolvedDataDir = $env:AGENT_DATA_DIR
}

Write-Info "Data directory: $ResolvedDataDir"

foreach ($sub in @("", "logs", "traces", "workspaces", "checkpoints")) {
    $d = if ($sub) { Join-Path $ResolvedDataDir $sub } else { $ResolvedDataDir }
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
Write-Success "Data directory created"

# ── .env configuration ────────────────────────────────────────────────────────
Write-Header "Configuration"

$EnvFile = Join-Path $ResolvedDataDir ".env"
if (Test-Path $EnvFile) {
    Write-Info ".env already exists — skipping (delete to regenerate: $EnvFile)"
} else {
    $EnvExample = Join-Path $ScriptDir ".env.example"
    if (-not (Test-Path $EnvExample)) { Fail ".env.example not found at $EnvExample" }
    Copy-Item $EnvExample $EnvFile
    Write-Success ".env written to $EnvFile"
    Write-Host
    Write-Warn "Review and edit the config before starting the server:"
    Write-Host "    $EnvFile" -ForegroundColor Yellow
    Write-Host "  Key settings:"
    Write-Host "    AGENT_API_LLM_PROVIDER   (ollama | openai | anthropic)"
    Write-Host "    AGENT_API_OPENAI_API_KEY (if using OpenAI)"
    Write-Host "    AGENT_API_DEFAULT_MODEL"
}

# ── Ollama detection ──────────────────────────────────────────────────────────
Write-Header "Checking Ollama"

$OllamaExe = Get-Command ollama -ErrorAction SilentlyContinue
if ($OllamaExe) {
    $OllamaVer = (& ollama --version 2>$null) -join ""
    Write-Success "Ollama found: $OllamaVer"

    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        Write-Success "Ollama daemon is reachable at http://127.0.0.1:11434"

        # Check if default model is pulled
        $defaultModel = (Select-String -Path $EnvFile -Pattern '^AGENT_API_DEFAULT_MODEL=(.*)' |
            ForEach-Object { $_.Matches.Groups[1].Value.Trim('"') } |
            Select-Object -First 1)
        if (-not $defaultModel) { $defaultModel = "qwen2.5-coder:7b" }

        $tags = ($resp.Content | ConvertFrom-Json).models.name
        $modelBase = $defaultModel.Split(':')[0]
        if ($tags -notmatch [regex]::Escape($modelBase)) {
            Write-Host
            Write-Warn "Default model '$defaultModel' not found locally."
            Write-Host "  Pull it with:  ollama pull $defaultModel" -ForegroundColor Cyan
        } else {
            Write-Success "Default model '$defaultModel' is available"
        }
    } catch {
        Write-Warn "Ollama daemon is not running. Start it with:  ollama serve"
    }
} else {
    Write-Warn "Ollama not found in PATH."
    Write-Host "  → Install from https://ollama.com  or configure OpenAI/Anthropic instead."
    Write-Host "    After installing, pull a model:  ollama pull qwen2.5-coder:7b"
}

# ── Node.js / frontend (optional) ─────────────────────────────────────────────
if (-not $NoFrontend) {
    Write-Header "Checking frontend dependencies (optional)"
    $FrontendDir = Join-Path $ScriptDir "frontend"
    if (Test-Path $FrontendDir) {
        $nodeExe = Get-Command node -ErrorAction SilentlyContinue
        if ($nodeExe) {
            $nodeVer = (& node --version 2>$null) -join ""
            Write-Success "Node.js $nodeVer"
            $pnpmExe = Get-Command pnpm -ErrorAction SilentlyContinue
            if ($pnpmExe) {
                Write-Info "Installing frontend dependencies..."
                Push-Location $FrontendDir
                try { & pnpm install --frozen-lockfile 2>&1 | Select-Object -Last 5 }
                finally { Pop-Location }
                Write-Success "Frontend dependencies installed"
                Write-Info "Build the frontend:  cd frontend ; pnpm build"
            } else {
                $npmExe = Get-Command npm -ErrorAction SilentlyContinue
                if ($npmExe) {
                    Write-Warn "pnpm not found — falling back to npm."
                    Push-Location $FrontendDir
                    try { & npm install 2>&1 | Select-Object -Last 5 }
                    finally { Pop-Location }
                    Write-Success "Frontend dependencies installed (npm)"
                } else {
                    Write-Warn "No package manager (pnpm/npm) found — skipping frontend."
                }
            }
        } else {
            Write-Warn "Node.js not found — frontend skipped. Install from https://nodejs.org"
        }
    } else {
        Write-Info "No frontend directory found — skipping."
    }
}

# ── locate entry-point scripts ────────────────────────────────────────────────
$BinDir = if (-not $NoVenv) {
    Join-Path (Join-Path $ScriptDir $VenvDir) "Scripts"
} else {
    Split-Path (Get-Command $PythonExe -ErrorAction SilentlyContinue).Source
}

# ── summary ───────────────────────────────────────────────────────────────────
Write-Host
Write-Host "  ════════════════════════════════════════" -ForegroundColor Green
Write-Host "   agent-mcp installation complete!" -ForegroundColor Green
Write-Host "  ════════════════════════════════════════" -ForegroundColor Green
Write-Host
Write-Host "  Data directory : " -NoNewline; Write-Host $ResolvedDataDir -ForegroundColor White
Write-Host "  Config file    : " -NoNewline; Write-Host $EnvFile -ForegroundColor White
Write-Host "  Database       : " -NoNewline; Write-Host (Join-Path $ResolvedDataDir "agent.db") -ForegroundColor White
Write-Host "  Logs           : " -NoNewline; Write-Host (Join-Path $ResolvedDataDir "logs\agent.log") -ForegroundColor White
Write-Host
Write-Host "  Next steps:" -ForegroundColor White
if (-not $NoVenv) {
    Write-Host "  1. Activate the environment:" -ForegroundColor White
    Write-Host "       $BinDir\Activate.ps1" -ForegroundColor Cyan
} else {
    Write-Host "  1. (No venv — commands available on PATH)" -ForegroundColor White
}
Write-Host "  2. Start the API server:" -ForegroundColor White
Write-Host "       agent-api" -ForegroundColor Cyan
Write-Host "  3. Open a new terminal and start the interactive shell:" -ForegroundColor White
Write-Host "       agent" -ForegroundColor Cyan
Write-Host
Write-Host "  Documentation  : README.md" -ForegroundColor Cyan
Write-Host
