# Downloads are explicit; no remote installer script is executed.
param([switch]$IncludeHermes)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Force '.local/tmp' | Out-Null
    $env:TEMP = Join-Path $projectRoot '.local/tmp'
    $env:TMP = $env:TEMP
    $env:UV_CACHE_DIR = Join-Path $projectRoot '.local/uv-cache'
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.local/python'
    $env:PYTHONUTF8 = '1'
    if (-not (Test-Path '.bootstrap/Scripts/uv.exe')) {
        & python -m venv .bootstrap
        if ($LASTEXITCODE -ne 0) { throw 'Bootstrap requires an installed Python with venv/pip.' }
        & ./.bootstrap/Scripts/python.exe -m pip install 'uv==0.13.6' --cache-dir .local/pip-cache
        if ($LASTEXITCODE -ne 0) { throw 'uv bootstrap failed.' }
    }
    & ./.bootstrap/Scripts/uv.exe python install 3.12.16 --no-bin
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 installation failed.' }
    & ./.bootstrap/Scripts/uv.exe sync --project backend --locked --python .local/python/cpython-3.12.16-windows-x86_64-none/python.exe
    if ($LASTEXITCODE -ne 0) { throw 'Backend lockfile sync failed.' }
    if ($IncludeHermes) {
        if (-not (Test-Path '.local/hermes-agent')) {
            & git clone --depth 1 --branch v0.22.5 https://github.com/NousResearch/hermes-agent.git .local/hermes-agent
            if ($LASTEXITCODE -ne 0) { throw 'Hermes checkout failed.' }
        }
        $hermesCommit = & git -C .local/hermes-agent rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or $hermesCommit -ne 'bf0203a794a07aac3ff764972ab9087baa4e4f4e') {
            throw 'Unexpected Hermes commit. Review before installing.'
        }
        & ./.bootstrap/Scripts/uv.exe python install 3.14.10 --no-bin
        if ($LASTEXITCODE -ne 0) { throw 'Hermes Python installation failed.' }
        & ./.bootstrap/Scripts/uv.exe sync --project .local/hermes-agent --locked --no-dev --extra messaging --python .local/python/cpython-3.14.10-windows-x86_64-none/python.exe
        if ($LASTEXITCODE -ne 0) { throw 'Hermes lockfile sync failed.' }
    }
    if (-not (Test-Path 'config/local.toml')) {
        Copy-Item -LiteralPath config/integrations.example.toml -Destination config/local.toml
    }
    Write-Host 'Local SDK setup complete. Account authentication and remote probes are separate.'
} finally {
    Pop-Location
}
