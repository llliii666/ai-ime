param(
    [switch]$CheckOnly,
    [switch]$NoStart,
    [switch]$SkipShortcut,
    [string]$ShortcutPath = "",
    [switch]$InstallWeasel,
    [switch]$OpenWeaselDownload
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

try {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    $OutputEncoding = [System.Text.UTF8Encoding]::new()
} catch {
}

$DataRoot = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "AIIME" } else { Join-Path $HOME ".aiime" }
$LogPath = Join-Path $DataRoot "bootstrap.log"

function Ensure-LogDir {
    New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
}

function Require-Command {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Missing command '$Name'. Install uv first, then run START_HERE.cmd again. Docs: https://docs.astral.sh/uv/getting-started/installation/"
    }
    return $command
}

function Invoke-LoggedUv {
    param(
        [string]$Label,
        [string[]]$Arguments
    )
    Ensure-LogDir
    Write-Host "== $Label =="
    Add-Content -LiteralPath $LogPath -Encoding utf8 -Value ""
    Add-Content -LiteralPath $LogPath -Encoding utf8 -Value "[$(Get-Date -Format s)] uv $($Arguments -join ' ')"
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & uv @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    Add-Content -LiteralPath $LogPath -Encoding utf8 -Value ($output | Out-String)
    if ($exitCode -ne 0) {
        Write-Host ($output | Out-String)
        throw "$Label failed with exit code $exitCode. Log: $LogPath"
    }
}

Write-Host "AI IME bootstrap"
Write-Host "Log: $LogPath"

$uv = Require-Command "uv"
Write-Host "uv: $($uv.Source)"

if ($CheckOnly) {
    Write-Host "Check passed. No files were changed."
    exit 0
}

Invoke-LoggedUv -Label "Install Python dependencies" -Arguments @("sync")

$onboardingArgs = @("run", "python", "-m", "ai_ime.onboarding")
if ($NoStart) {
    $onboardingArgs += "--no-start"
}
if ($SkipShortcut) {
    $onboardingArgs += "--skip-shortcut"
}
if ($ShortcutPath.Trim()) {
    $onboardingArgs += @("--shortcut-path", $ShortcutPath.Trim())
}
if ($InstallWeasel) {
    $onboardingArgs += "--install-weasel"
}
if ($OpenWeaselDownload) {
    $onboardingArgs += "--open-weasel-download"
}

& uv @onboardingArgs
if ($LASTEXITCODE -ne 0) {
    throw "AI IME onboarding failed with exit code $LASTEXITCODE."
}
