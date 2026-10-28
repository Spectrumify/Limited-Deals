# Makes the dashboard start automatically (minimized) when you log in to Windows.
# Run:  powershell -ExecutionPolicy Bypass -File install-startup.ps1
# Undo: powershell -ExecutionPolicy Bypass -File remove-startup.ps1

$project = $PSScriptRoot
$python = Join-Path $project "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "venv not found. Create it first (see CLAUDE.md)."
    exit 1
}

$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "Limited Deals.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python
$shortcut.Arguments = "app.py"
$shortcut.WorkingDirectory = $project
$shortcut.WindowStyle = 7  # 7 = start minimized
$shortcut.Description = "Limited Deals dashboard (http://127.0.0.1:5000)"
$shortcut.Save()

Write-Output "Installed: $shortcutPath"
Write-Output "It will start minimized at your next login. Close its window to stop it."
