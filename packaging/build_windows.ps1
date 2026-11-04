# Build BachHoa705 for Windows. Run in PowerShell from the repo root:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# Output: packaging\dist\BachHoa705\ (portable folder) + packaging\dist\BachHoa705-windows.zip
#
# One-time setup before the first run: uv (https://astral.sh/uv).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "== uv sync =="
uv sync

Write-Host "== pytest =="
uv run pytest -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

if (Test-Path packaging\build) { Remove-Item -Recurse -Force packaging\build }
if (Test-Path packaging\dist) { Remove-Item -Recurse -Force packaging\dist }

Write-Host "== pyinstaller =="
uv run pyinstaller packaging\shop.spec --distpath packaging\dist --workpath packaging\build --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$appExe = "packaging\dist\BachHoa705\BachHoa705.exe"
if (-not (Test-Path $appExe)) { throw "Build did not produce $appExe" }

Write-Host "== self-test =="
$selftestData = Join-Path $env:TEMP "shopapp-selftest-data"
$selftestOut = Join-Path $env:TEMP "shopapp-selftest-out"
if (Test-Path $selftestData) { Remove-Item -Recurse -Force $selftestData }
if (Test-Path $selftestOut) { Remove-Item -Recurse -Force $selftestOut }
$env:SHOP_DATA_DIR = $selftestData
$env:SHOP_SELFTEST_OUT = $selftestOut
$p = Start-Process -FilePath $appExe -ArgumentList "--self-test" -Wait -PassThru
$resultPath = Join-Path $selftestOut "result.txt"
$result = if (Test-Path $resultPath) { Get-Content $resultPath } else { @() }
if ($p.ExitCode -ne 0 -or $result.Count -eq 0 -or $result[0] -ne "OK") {
    Write-Host ($result -join "`n")
    throw "Self-test failed (exit code $($p.ExitCode))"
}
Write-Host "Self-test OK: $($result -join ' | ')"

Write-Host "== zip =="
$zipPath = "packaging\dist\BachHoa705-windows.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path "packaging\dist\BachHoa705" -DestinationPath $zipPath -Force
Write-Host "Done: $zipPath"
