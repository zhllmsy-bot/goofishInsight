Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = [string](Get-Command python -CommandType Application | Select-Object -First 1 -ExpandProperty Source)

Set-Location $repoRoot
$env:PYTHONPATH = Join-Path $repoRoot "apps\collector\src"

& $python "scripts/run_discovery_job.py" @args
exit $LASTEXITCODE
