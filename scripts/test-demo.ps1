[CmdletBinding()]
param(
    [string]$WorkerUrl = "http://127.0.0.1:8001"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sample = Join-Path $root "samples\two-warehouse-items-qr.png"

foreach ($endpoint in @(
    "http://127.0.0.1:5173/",
    "http://127.0.0.1:5080/health/live",
    "$WorkerUrl/health/live"
)) {
    $response = Invoke-WebRequest -Uri $endpoint -UseBasicParsing -TimeoutSec 10
    Write-Host "$($response.StatusCode) $endpoint"
}

if (-not (Test-Path $sample)) {
    throw "Sample QR image was not found: $sample"
}

$json = & curl.exe -sS -X POST `
    -F "photo=@$sample;type=image/png" `
    -F "warehouseId=WH-BKK-01" `
    -F "itemId=ITEM-204" `
    "$WorkerUrl/position/locate"

if ($LASTEXITCODE -ne 0) {
    throw "QR upload test failed."
}

$result = $json | ConvertFrom-Json
Write-Host "Detection: $($result.detectionStatus)"
Write-Host "Position: $($result.positionStatus)"
Write-Host "QR count: $($result.detections.qr.Count)"
Write-Host "Event count: $($result.events.Count)"
Write-Host "Multi-QR smoke test passed."
