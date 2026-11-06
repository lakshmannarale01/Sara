$ErrorActionPreference = 'Stop'
$taskName = 'SARA Reminders'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$worker = Join-Path $PSScriptRoot 'sara_reminder_worker.py'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "SARA Python environment not found at $python. Start SARA once to complete setup, then run this installer again."
}
if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
    throw "Reminder worker not found at $worker."
}

$actionText = '"{0}" "{1}"' -f $python, $worker
& schtasks.exe /Create /TN $taskName /SC MINUTE /MO 1 /TR $actionText /IT /F
if ($LASTEXITCODE -ne 0) {
    throw "Windows could not register the '$taskName' task (exit code $LASTEXITCODE)."
}
Write-Host "Installed '$taskName' for the current Windows user. It checks once a minute while that user is signed in."
Write-Host "Remove it with: .\uninstall_sara_reminders.ps1"
