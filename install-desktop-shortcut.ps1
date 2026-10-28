# Puts a "Limited Deals" icon on your desktop that opens the online dashboard (GitHub Pages).
# Run:  powershell -ExecutionPolicy Bypass -File install-desktop-shortcut.ps1
#
# (To run the old local version instead, double-click launch.pyw in this folder.)

$url = "https://spectrumify.github.io/Limited-Deals/"
$desktop = [Environment]::GetFolderPath("Desktop")

# Remove the older shortcut that started the local server.
$oldShortcut = Join-Path $desktop "Limited Deals.lnk"
if (Test-Path $oldShortcut) { Remove-Item $oldShortcut }

$shortcutPath = Join-Path $desktop "Limited Deals.url"
Set-Content -Path $shortcutPath -Encoding ASCII -Value "[InternetShortcut]`r`nURL=$url"
Write-Output "Created: $shortcutPath -> $url"
