# Registers a Windows Task Scheduler task that starts Gita Sarathi Live when you sign in,
# and restarts it if it fails. Run once in PowerShell from this folder:
#   powershell -ExecutionPolicy Bypass -File .\install_autopilot.ps1
# Remove it later with:  Unregister-ScheduledTask -TaskName "GitaSarathiLive" -Confirm:$false
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force -Path (Join-Path $here "logs") | Out-Null
$action = New-ScheduledTaskAction -Execute (Join-Path $here "start_gitalive.bat") -WorkingDirectory $here
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT1M"   # let Windows and the network settle first
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName "GitaSarathiLive" -Action $action -Trigger $trigger -Settings $settings `
  -Description "Gita Sarathi 24/7 YouTube stream" -Force | Out-Null
Write-Host "Done. Gita Sarathi Live will start one minute after you sign in to Windows."
Write-Host "Start it now with:  Start-ScheduledTask -TaskName GitaSarathiLive"
