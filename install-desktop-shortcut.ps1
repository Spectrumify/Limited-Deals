# Puts a "Limited Deals" shortcut on your desktop. Double-click it to open the dashboard
# (it starts the server first if it isn't already running).
# Run:  powershell -ExecutionPolicy Bypass -File install-desktop-shortcut.ps1

$project = $PSScriptRoot
$pythonw = Join-Path $project "venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "venv not found. Create it first (see CLAUDE.md)."
    exit 1
}

$shortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "Limited Deals.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "launch.pyw"
$shortcut.WorkingDirectory = $project
$shortcut.Description = "Open the Limited Deals dashboard"
$shortcut.Save()

Write-Output "Created: $shortcutPath"
