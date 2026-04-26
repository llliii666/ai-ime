param(
    [string]$Version = "",
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
    Write-Host "AI IME release build check"
    Write-Host "Project: $ProjectRoot"
    Write-Host "Version override: $Version"
    Write-Host "Planned steps: tests, UI smoke check, Python package build, PyInstaller one-folder build."
    Write-Host "No files were changed."
    exit 0
}

uv run python -m unittest discover -s tests
uv run python -m ai_ime.settings_window --smoke
uv build --no-sources

uvx pyinstaller --clean --noconfirm packaging/pyinstaller/ai-ime.spec

$ArtifactRoot = Join-Path $ProjectRoot "dist"
$AppDir = Join-Path $ArtifactRoot "AI IME"
if (-not (Test-Path -LiteralPath $AppDir)) {
    throw "PyInstaller output was not found: $AppDir"
}

$Suffix = if ($Version) { $Version } else { (Get-Date -Format "yyyyMMdd-HHmmss") }
$ZipPath = Join-Path $ArtifactRoot "AI-IME-$Suffix-windows.zip"
if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath
}
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $ZipPath
Write-Host "Release artifact: $ZipPath"
