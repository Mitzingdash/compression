@echo off
rem One-time setup: unblocks SmartCompress.ps1, fixes execution policy, then deletes itself.
rem After this runs, just right-click SmartCompress.ps1 -> "Run with PowerShell".

set "SC_LAUNCHER=%~dp0SmartCompress.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -LiteralPath $env:SC_LAUNCHER; Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SC_LAUNCHER%"
del "%~f0"
