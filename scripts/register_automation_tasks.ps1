$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Virtual environment Python was not found at $python" }

$dailyAction = New-ScheduledTaskAction -Execute $python -Argument 'manage.py daily_provider_automation' -WorkingDirectory $projectRoot
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At 6:00AM
$dailySettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName 'FoodBankHub Daily Provider Automation' -Action $dailyAction -Trigger $dailyTrigger -Settings $dailySettings -Description 'Generate provider forecasts, update urgent needs, send stock alerts, and apply configured self-report retention.' -Force | Out-Null

$weeklyForecastAction = New-ScheduledTaskAction -Execute $python -Argument 'manage.py retrain_weekly_forecasts' -WorkingDirectory $projectRoot
$weeklyForecastTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 2:00AM
$weeklyForecastSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 4)
Register-ScheduledTask -TaskName 'FoodBankHub Weekly Forecast Retraining' -Action $weeklyForecastAction -Trigger $weeklyForecastTrigger -Settings $weeklyForecastSettings -Description 'Refresh and retain the weekly provider forecast snapshots.' -Force | Out-Null

$backupAction = New-ScheduledTaskAction -Execute $python -Argument 'manage.py backup_database' -WorkingDirectory $projectRoot
$backupTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3:00AM
$backupSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName 'FoodBankHub Weekly Database Backup' -Action $backupAction -Trigger $backupTrigger -Settings $backupSettings -Description 'Create and rotate a compressed FoodBankHub MySQL backup.' -Force | Out-Null

Get-ScheduledTask -TaskName 'FoodBankHub Daily Provider Automation','FoodBankHub Weekly Forecast Retraining','FoodBankHub Weekly Database Backup' | Select-Object TaskName, State
