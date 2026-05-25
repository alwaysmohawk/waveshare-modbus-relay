# Waveshare Modbus Relay - Windows Service Installer

$ErrorActionPreference = "Stop"
Start-Transcript -Path "$PSScriptRoot\install.log" -Append

# Self-elevate if not running as admin

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Relaunching as Administrator..."
    Start-Process powershell "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

# Helpers

function Write-Step { param($msg) Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "   OK: $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "   WARN: $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "   ERROR: $msg" -ForegroundColor Red; exit 1 }

# Verify we're in the repo root

$RepoRoot = $PSScriptRoot
if (-not (Test-Path "$RepoRoot\pyproject.toml")) {
    Write-Fail "Run this script from the waveshare-modbus-relay repo root"
}

# Prompts

Write-Host "`nWaveshare Modbus Relay - Service Installer" -ForegroundColor Green
Write-Host "Press Enter to accept the default shown in brackets.`n"

$RelayHost = Read-Host "Relay device IP    [192.168.1.200]"
if (-not $RelayHost) { $RelayHost = "192.168.1.200" }

$RelayPort = Read-Host "Relay device port  [502]"
if (-not $RelayPort) { $RelayPort = "502" }

$ApiPort = Read-Host "API port           [8001]"
if (-not $ApiPort) { $ApiPort = "8001" }

$ServiceName = Read-Host "Service name       [waveshare-relay]"
if (-not $ServiceName) { $ServiceName = "waveshare-relay" }

# Install uv

Write-Step "Checking uv..."

$UvPath = "$env:USERPROFILE\.local\bin\uv.exe"
if (-not (Test-Path $UvPath)) {
    $UvPath = (Get-Command uv -ErrorAction SilentlyContinue).Source
}

if (-not $UvPath -or -not (Test-Path $UvPath)) {
    Write-Host "   Installing uv..."
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $UvPath = "$env:USERPROFILE\.local\bin\uv.exe"
}

if (-not (Test-Path $UvPath)) {
    Write-Fail "uv installation failed - install manually from https://docs.astral.sh/uv"
}
Write-Ok "uv at $UvPath"

# Install Python dependencies

Write-Step "Installing dependencies..."
& $UvPath sync --project $RepoRoot
if ($LASTEXITCODE -ne 0) { Write-Fail "uv sync failed" }
Write-Ok "Dependencies ready"

# Install NSSM

Write-Step "Checking NSSM..."

$NssmPath = (Get-Command nssm -ErrorAction SilentlyContinue).Source

if (-not $NssmPath) {
    Write-Host "   Installing NSSM via winget..."
    winget install NSSM.NSSM --silent --source winget --accept-package-agreements --accept-source-agreements

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $NssmPath = (Get-Command nssm -ErrorAction SilentlyContinue).Source
}

if (-not $NssmPath) {
    Write-Fail "NSSM not found after install - restart this terminal and re-run install.ps1"
}
Write-Ok "NSSM at $NssmPath"

# Register service

Write-Step "Registering service '$ServiceName'..."

$ErrorActionPreference = "Continue"
$null = & $NssmPath status $ServiceName 2>$null
$serviceExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"

if ($serviceExists) {
    Write-Warn "Service '$ServiceName' already exists - removing and re-registering"
    & $NssmPath stop $ServiceName 2>$null | Out-Null
    & $NssmPath remove $ServiceName confirm 2>$null | Out-Null
}

$UvArgs = "run waveshare-modbus --headless --relay-host $RelayHost --relay-port $RelayPort --api-port $ApiPort"

& $NssmPath install     $ServiceName $UvPath $UvArgs
& $NssmPath set         $ServiceName AppDirectory   $RepoRoot
& $NssmPath set         $ServiceName AppExit         Default Restart
& $NssmPath set         $ServiceName AppRestartDelay 3000
& $NssmPath set         $ServiceName Description    "Waveshare Modbus Relay REST API"
& $NssmPath set         $ServiceName Start           SERVICE_AUTO_START

Write-Ok "Service registered"

# Start service

Write-Step "Starting service..."
& $NssmPath start $ServiceName

if ($LASTEXITCODE -ne 0) {
    Write-Warn "Service did not start cleanly. Check with: nssm status $ServiceName"
} else {
    Write-Ok "Service started"
}

# Summary

Write-Host "`n----------------------------------------" -ForegroundColor Green
Write-Host " Install complete" -ForegroundColor Green
Write-Host "----------------------------------------" -ForegroundColor Green
Write-Host " Service  : $ServiceName"
Write-Host " Relay    : $RelayHost`:$RelayPort"
Write-Host " API      : http://localhost:$ApiPort"
Write-Host " Docs     : http://localhost:$ApiPort/docs"
Write-Host ""
Write-Host " Useful commands:"
Write-Host "   nssm status $ServiceName"
Write-Host "   nssm restart $ServiceName"
Write-Host "   nssm stop $ServiceName"
Write-Host "   nssm remove $ServiceName confirm"
Write-Host "----------------------------------------`n" -ForegroundColor Green
