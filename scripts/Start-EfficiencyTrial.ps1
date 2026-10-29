param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$principal = [Security.Principal.WindowsPrincipal]::new([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $arguments = @('-NoProfile','-File',('"' + $PSCommandPath + '"'))
    if ($OutputDirectory) { $arguments += @('-OutputDirectory',('"' + $OutputDirectory + '"')) }
    Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe') -Verb RunAs -ArgumentList $arguments -WindowStyle Hidden | Out-Null
    return
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $root ('results\efficiency-trial-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$resolved = [IO.Path]::GetFullPath($OutputDirectory)
$resultsRoot = Join-Path $root 'results'
if (-not $resolved.StartsWith($resultsRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Use a results directory in this project' }
if (Test-Path -LiteralPath $resolved) { throw 'Choose a new results directory; existing measurements are preserved' }
New-Item -ItemType Directory -Path $resolved | Out-Null
Set-Content -LiteralPath (Join-Path $resultsRoot 'latest-efficiency-trial.txt') -Value $resolved -Encoding UTF8
Set-Location -LiteralPath $root
$pythonPath = Join-Path $root '.venv\Scripts\python.exe'
$previousPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & $pythonPath -X utf8 (Join-Path $root 'bench\gemm.py') --output (Join-Path $resolved 'before.json') --label 'Fresh reference for temporary efficiency trial' *> (Join-Path $resolved 'reference-console.log')
    if ($LASTEXITCODE -ne 0) { throw 'Reference benchmark failed; no offset trial performed' }
    & $pythonPath -X utf8 (Join-Path $root 'bench\efficiency.py') --trial --output-directory $resolved *> (Join-Path $resolved 'trial-console.log')
    $trialExit = $LASTEXITCODE
    & $pythonPath -X utf8 (Join-Path $root 'bench\report_efficiency.py') $resolved *> (Join-Path $resolved 'report-console.log')
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($trialExit -ne 0) { throw ('Trial stopped. Inspect ' + (Join-Path $resolved 'efficiency-summary.json')) }
