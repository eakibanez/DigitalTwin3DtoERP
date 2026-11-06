[CmdletBinding()]
param(
    [switch]$Tunnel
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$frontend = Join-Path $root "frontend"
$apiProject = Join-Path $root "services\integration-api"
$worker = Join-Path $root "services\position-worker"
$python = Join-Path $worker ".venv\Scripts\python.exe"

function Require-Command([string]$name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        throw "Required command '$name' was not found in PATH."
    }
}

Require-Command "npm"
$dotnetCommand = Get-Command "dotnet" -ErrorAction SilentlyContinue
$dotnetExe = if ($dotnetCommand) { $dotnetCommand.Source } else { "C:\Program Files\dotnet\dotnet.exe" }
if (-not (Test-Path $dotnetExe)) {
    throw "Required .NET SDK was not found. Install .NET 8 SDK."
}
if (-not (Test-Path $python)) {
    throw "Python environment is missing. Run: py -3.12 -m venv `"$worker\.venv`" and pip install -r `"$worker\requirements.txt`""
}

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    throw "Frontend dependencies are missing. Run: npm --prefix `"$frontend`" install"
}

$api = Start-Process powershell.exe -PassThru -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-Command",
    "& '$dotnetExe' run --project '$apiProject' --urls http://0.0.0.0:5080"
)
$workerProcess = Start-Process powershell.exe -PassThru -WorkingDirectory $worker -ArgumentList @(
    "-NoExit", "-Command",
    "& '$python' -m uvicorn app:app --app-dir '$worker' --host 0.0.0.0 --port 8001"
)
$frontendProcess = Start-Process powershell.exe -PassThru -WorkingDirectory $frontend -ArgumentList @(
    "-NoExit", "-Command",
    "npm run dev -- --host 0.0.0.0"
)

Write-Host "Started API PID=$($api.Id), worker PID=$($workerProcess.Id), frontend PID=$($frontendProcess.Id)"
$lanIp = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1 -ExpandProperty IPAddress
Write-Host "LAN URL: http://$lanIp`:5173"

if ($Tunnel) {
    $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cloudflared) {
        $cloudflaredPath = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
        if (Test-Path $cloudflaredPath) {
            $cloudflaredExe = $cloudflaredPath
        } else {
            throw "cloudflared was not found. Install it or run without -Tunnel."
        }
    } else {
        $cloudflaredExe = $cloudflared.Source
    }
    $tunnelProcess = Start-Process powershell.exe -PassThru -WorkingDirectory $root -ArgumentList @(
        "-NoExit", "-Command", "& '$cloudflaredExe' tunnel --url http://127.0.0.1:5173"
    )
    Write-Host "Started HTTPS tunnel PID=$($tunnelProcess.Id). Use the URL printed in its window."
}

Start-Sleep -Seconds 3
foreach ($endpoint in @("http://127.0.0.1:5080/health/live", "http://127.0.0.1:8001/health/live", "http://127.0.0.1:5173/")) {
    try {
        $response = Invoke-WebRequest -Uri $endpoint -UseBasicParsing -TimeoutSec 10
        Write-Host "$($response.StatusCode) $endpoint"
    } catch {
        Write-Warning "Health check failed: $endpoint"
    }
}

Write-Host "Open the HTTPS tunnel URL on iPhone, then use samples/two-warehouse-items-qr.png for multi-QR testing."
