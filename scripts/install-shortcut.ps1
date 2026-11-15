# Creates a "Moyo" desktop shortcut with the global hotkey Ctrl+Alt+M.
# Optional: -Startup also starts Moyo quietly when you log in to Windows.
# Undo: delete "Moyo.lnk" from your Desktop (and from shell:startup if you used -Startup).
param([switch]$Startup)

$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root "moyo.cmd"
$shell = New-Object -ComObject WScript.Shell

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = $shell.CreateShortcut((Join-Path $desktop "Moyo.lnk"))
$lnk.TargetPath = $target
$lnk.WorkingDirectory = $root
$lnk.WindowStyle = 7          # minimized: no console flash
$lnk.Hotkey = "CTRL+ALT+M"
$lnk.Description = "Moyo AI: personal executive assistant"
$lnk.Save()
Write-Output "Desktop shortcut created. Press Ctrl+Alt+M anywhere to open Moyo."

$day = $shell.CreateShortcut((Join-Path $desktop "Start my day.lnk"))
$day.TargetPath = $target
$day.Arguments = "--start-day"
$day.WorkingDirectory = $root
$day.WindowStyle = 7
$day.Hotkey = "CTRL+ALT+S"
$day.Description = "Moyo: open your workspace, start music and read the briefing"
$day.Save()
Write-Output "Start-my-day shortcut created. Press Ctrl+Alt+S to start your day."

if ($Startup) {
    $startupDir = [Environment]::GetFolderPath("Startup")
    $s = $shell.CreateShortcut((Join-Path $startupDir "Moyo.lnk"))
    $s.TargetPath = (Join-Path $root ".venv\Scripts\pythonw.exe")
    $s.Arguments = "-m moyo --no-window"
    $s.WorkingDirectory = $root
    $s.WindowStyle = 7
    $s.Save()
    Write-Output "Moyo will also start in the background when you log in."
}
