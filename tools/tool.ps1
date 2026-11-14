param([Parameter(ValueFromRemainingArguments=$true)][string[]]$ToolArguments)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonPath = Join-Path $projectRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run tools/setup.ps1 first.' }
$tempPath = Join-Path $projectRoot '.local/tmp'
New-Item -ItemType Directory -Force -Path $tempPath | Out-Null
$env:TEMP = $tempPath
$env:TMP = $tempPath
$env:PYTHONUTF8 = '1'
& $pythonPath -m mail_tools.cli @ToolArguments
exit $LASTEXITCODE
