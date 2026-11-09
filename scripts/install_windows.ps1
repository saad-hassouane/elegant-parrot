# Windows installer (PowerShell 5.1+). Usage:  powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 [-Autostart]
#   -Autostart   put a shortcut in your Startup folder so `elegant-parrot listen` starts at login (opt-in)
# NOTE: written against documented Win32 APIs; not yet run on real hardware.
param([switch]$Autostart)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Install Python 3.10+ first (https://www.python.org/downloads/)" }
python -m venv "$Root\.venv"
& "$Root\.venv\Scripts\pip.exe" install -q -e "$Root[ner,corrector,desktop]"
& "$Root\.venv\Scripts\python.exe" -m spacy download en_core_web_sm fr_core_news_sm
& "$Root\.venv\Scripts\elegant-parrot.exe" init
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Write-Host "Install Ollama: winget install Ollama.Ollama   then: ollama pull llama3.2:3b" }
if ($Autostart) {
  $lnk = Join-Path ([Environment]::GetFolderPath("Startup")) "Elegant Parrot.lnk"
  $sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
  $sh.TargetPath = "$Root\.venv\Scripts\pythonw.exe"; $sh.Arguments = "-m corrector.listen"; $sh.WorkingDirectory = $Root; $sh.Save()
  Write-Host "Startup shortcut created: $lnk"
}
Write-Host "Check:  $Root\.venv\Scripts\elegant-parrot.exe doctor"
Write-Host "Run:    $Root\.venv\Scripts\elegant-parrot.exe listen      (shortcut: Ctrl+Shift+E)"
