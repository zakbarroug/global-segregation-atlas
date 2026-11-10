# Launch the installed application locally; no logs or datasets are written.
param([switch]$Development)
$ErrorActionPreference = 'Stop'
$env:NEXT_TELEMETRY_DISABLED = '1'
$atlasRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$atlasPython = Join-Path $atlasRoot '.venv\Scripts\python.exe'
$atlasNode = (Get-Command node -ErrorAction Stop).Source
$atlasNext = Join-Path $atlasRoot 'apps\web\node_modules\next\dist\bin\next'
if (!(Test-Path -LiteralPath $atlasPython) -or !(Test-Path -LiteralPath $atlasNext)) {
    throw 'Install dependencies first using README.md.'
}
if (!(Test-Path -LiteralPath (Join-Path $atlasRoot '.env'))) {
    throw 'Copy .env.example to .env and configure your developer credentials.'
}
foreach ($atlasPort in @(8000, 3000)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $atlasPort -ErrorAction SilentlyContinue) {
        throw "Port $atlasPort is already in use. Stop the existing atlas server or use it."
    }
}
if (!$Development -and !(Test-Path -LiteralPath (Join-Path $atlasRoot 'apps\web\.next\BUILD_ID'))) {
    throw 'Run npm run build in apps/web first, or use -Development.'
}
$atlasApi = Start-Process -FilePath $atlasPython -ArgumentList @('-m','uvicorn','src.main:app','--host','127.0.0.1','--port','8000','--no-access-log') -WorkingDirectory $atlasRoot -WindowStyle Hidden -PassThru
$atlasMode = if ($Development) { 'dev' } else { 'start' }
$atlasWeb = Start-Process -FilePath $atlasNode -ArgumentList @(('"' + $atlasNext + '"'),$atlasMode,'--hostname','127.0.0.1','--port','3000') -WorkingDirectory (Join-Path $atlasRoot 'apps\web') -WindowStyle Hidden -PassThru
Write-Output "Atlas: http://127.0.0.1:3000 | API PID $($atlasApi.Id), Web PID $($atlasWeb.Id)."
Write-Output "Stop only these launched processes with: Stop-Process -Id $($atlasApi.Id),$($atlasWeb.Id)"
