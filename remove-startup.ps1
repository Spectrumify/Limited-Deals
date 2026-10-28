# Stops the dashboard from starting automatically at login.
# Run:  powershell -ExecutionPolicy Bypass -File remove-startup.ps1

$shortcutPath = Join-Path ([Environment]::GetFolderPath("Startup")) "Limited Deals.lnk"
if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath
    Write-Output "Removed: $shortcutPath"
} else {
    Write-Output "Nothing to remove (not installed)."
}
