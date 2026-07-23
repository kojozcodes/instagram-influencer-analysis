# Temporary PUBLIC preview link, run from this Windows machine.
# Starts the app locally and exposes it via a Cloudflare quick tunnel
# (free, no account, no signup). Prints a public https URL to share.
#
#   powershell -ExecutionPolicy Bypass -File deploy\preview_windows.ps1
#
# Stop with Ctrl+C. The URL is temporary and changes each run.

$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $PSScriptRoot
Set-Location $proj

# 1. cloudflared (download once, ~17MB)
$cf = Join-Path $proj "cloudflared.exe"
if (-not (Test-Path $cf)) {
  Write-Host "Downloading cloudflared..." -ForegroundColor Cyan
  $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
  Invoke-WebRequest -Uri $url -OutFile $cf
}

# 2. start the app (background)
Write-Host "Starting the analysis app on http://localhost:8000 ..." -ForegroundColor Cyan
$app = Start-Process -FilePath "python" `
  -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000" `
  -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4

# 3. open the tunnel (foreground — prints the public URL)
Write-Host ""
Write-Host "Opening public tunnel. Share the https://<...>.trycloudflare.com URL below." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop everything." -ForegroundColor Yellow
Write-Host ""
try {
  & $cf tunnel --url http://localhost:8000
} finally {
  if ($app -and -not $app.HasExited) { Stop-Process -Id $app.Id -Force }
  Write-Host "Preview stopped." -ForegroundColor Cyan
}
