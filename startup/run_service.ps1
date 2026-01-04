# Simple PowerShell script to run orchestrator.py in a loop
# This acts as a persistent background-ready process

$scriptPath = "$PSScriptRoot\..\orchestrator.py"

Write-Host "Starting Outlook Orchestrator Service..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop."

while ($true) {
    Write-Host "[$(Get-Date)] Executing Orchestrator..." -ForegroundColor Gray
    # Run the python script
    python $scriptPath
    
    # If the script exits, wait 5 seconds and restart
    Write-Host "[$(Get-Date)] Orchestrator exited. Restarting in 5 seconds..." -ForegroundColor Red
    Start-Sleep -Seconds 5
}
