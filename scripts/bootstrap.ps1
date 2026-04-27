param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing command '$Name'. Install it first and re-run this script."
    }
}

Require-Command "uv"

if ($CheckOnly) {
    Write-Host "AI IME bootstrap check"
    Write-Host "Project: $ProjectRoot"
    Write-Host "uv: $((Get-Command uv).Source)"
    Write-Host "No files were changed."
    exit 0
}

uv sync

if (-not (Test-Path -LiteralPath ".env") -and (Test-Path -LiteralPath ".env.example")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Created .env from .env.example. Fill in your API key before using cloud providers."
}

uv run python -m ai_ime setup
uv run python -m ai_ime create-shortcut

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Desktop shortcut created. Start the tray app by double-clicking AI IME, or run:"
Write-Host "  uv run python run.py"
