Set-Location $PSScriptRoot
Write-Host "Starting Email Orchestrator Web Dashboard..." -ForegroundColor Green
Write-Host "Please open http://localhost:8000 in your browser." -ForegroundColor Cyan

# Check if port 8000 is in use (Initial cleanup)
$portStatus = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($portStatus) {
    Write-Host "Cleaning up existing process on port 8000..." -ForegroundColor Yellow
    Get-Process -Id $portStatus.OwningProcess -ErrorAction SilentlyContinue | Stop-Process -Force
}

while ($true) {
    Write-Host "[$(Get-Date)] Starting Jasper Web Dashboard..." -ForegroundColor Green
    python ..\app.py
    
    Write-Host "[$(Get-Date)] Jasper exited. Restarting in 2 seconds..." -ForegroundColor Red
    Start-Sleep -Seconds 2
}
