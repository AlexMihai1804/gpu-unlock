# Ordinary user launcher. UAC is used only to read the internal log and trust variables.
param([ValidateRange(10,3600)][int]$Seconds=1200)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
Set-Location -LiteralPath $root
$out=Join-Path $root ('results\long-benchmark-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $out) { throw 'Output directory already exists.' }
New-Item -ItemType Directory -Path $out | Out-Null
$out | Set-Content -LiteralPath (Join-Path $root 'results\latest-long-benchmark.txt') -Encoding UTF8
$boot=(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime()
[ordered]@{utc=(Get-Date).ToUniversalTime().ToString('o');boot_utc=$boot.ToString('o');pid=$PID;target_seconds=$Seconds} |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'launch.json') -Encoding UTF8
$python=Join-Path $root '.venv\Scripts\python.exe'
$collection=Join-Path $out 'automatic-boot'
$collector=Join-Path $PSScriptRoot 'Collect-InternalAutomatic.ps1'
$arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$collector+'" -OutputDirectory "'+$collection+'"'
Write-Output 'Accept the read-only UAC collector. No boot configuration will be written.'
$process=Start-Process -FilePath powershell.exe -Verb RunAs -WindowStyle Hidden -ArgumentList $arguments -PassThru
$process.WaitForExit()
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $collection 'collection-complete.json'))) { throw 'Read-only automatic boot collection did not complete.' }
& $python -X utf8 'tools\review_automatic.py' --evidence $collection
if ($LASTEXITCODE -ne 0) { throw 'Automatic boot trust/transaction review failed.' }
Copy-Item -LiteralPath (Join-Path $collection 'automatic-review.json') -Destination (Join-Path $out 'review-boot.json')
$before=Join-Path $out 'before.json'
& $python -X utf8 'bench\gemm.py' --n 8192 --samples 5 --iterations 10 --warmup 4 --device 0 --label automatic-before-long --output $before
if ($LASTEXITCODE -ne 0) { throw 'Pre-test numerical benchmark failed.' }
& $python -X utf8 'tools\review_automatic.py' --evidence $collection --benchmark $before
if ($LASTEXITCODE -ne 0) { throw 'Pre-test review failed.' }
Copy-Item -LiteralPath (Join-Path $collection 'automatic-review.json') -Destination (Join-Path $out 'review-before.json')
$review=Get-Content -LiteralPath (Join-Path $collection 'automatic-review.json') -Raw | ConvertFrom-Json
if (-not $review.performance_matches_unlocked_pattern -or -not $review.all_outputs_bit_identical) {
    throw 'Current performance does not match the previously verified unlocked pattern. Long unlocked test not started; preserve these results and report the state.'
}
& $python -X utf8 'bench\endurance.py' --seconds $Seconds --iterations 100 --output-directory (Join-Path $out 'endurance')
if ($LASTEXITCODE -ne 0) { throw 'Endurance test stopped. Read endurance\summary.json.' }
$after=Join-Path $out 'after.json'
& $python -X utf8 'bench\gemm.py' --n 8192 --samples 5 --iterations 10 --warmup 4 --device 0 --label automatic-after-long --output $after
if ($LASTEXITCODE -ne 0) { throw 'Post-test numerical benchmark failed.' }
& $python -X utf8 'tools\review_automatic.py' --evidence $collection --benchmark $after
if ($LASTEXITCODE -ne 0) { throw 'Post-test review failed.' }
Copy-Item -LiteralPath (Join-Path $collection 'automatic-review.json') -Destination (Join-Path $out 'review-after.json')
$afterReview=Get-Content -LiteralPath (Join-Path $out 'review-after.json') -Raw | ConvertFrom-Json
if (-not $afterReview.performance_matches_unlocked_pattern -or -not $afterReview.all_outputs_bit_identical) { throw 'Post-test output or unlocked performance pattern failed.' }
& (Join-Path $PSScriptRoot 'Collect-NormalBootControl.ps1') -OutputDirectory (Join-Path $out 'health-after')
& $python -X utf8 'bench\report_endurance.py' --directory $out
if ($LASTEXITCODE -ne 0) { throw 'Final endurance review did not pass.' }
Write-Output ('Long benchmark finished. Results: '+$out)
