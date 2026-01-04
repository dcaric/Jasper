$currentDir = $PSScriptRoot
$scriptPath = Join-Path $currentDir "run_web.ps1"
$taskName = "EmailOrchestratorDashboard"

Write-Host "Setting up Email Orchestrator to start at login..." -ForegroundColor Green

# Create the action (running the powershell script)
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

# Create the trigger (at log on)
$trigger = New-ScheduledTaskTrigger -AtLogOn

# Register the task
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName $taskName -Description "Runs the Email Orchestrator Web Dashboard at login." -Force

Write-Host "SUCCESS: The dashboard will now start automatically whenever you log in." -ForegroundColor Cyan
Write-Host "You can find it in 'Task Scheduler' under the name '$taskName'." -ForegroundColor Cyan
