$ErrorActionPreference = 'Stop'
$taskName = 'SARA Reminders'
& schtasks.exe /Delete /TN $taskName /F
if ($LASTEXITCODE -ne 0) {
    throw "Windows could not remove the '$taskName' task (exit code $LASTEXITCODE)."
}
Write-Host "Removed '$taskName'. Your saved reminders remain in SARA's local data."
