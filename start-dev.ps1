# start-dev.ps1 — Kill old processes and restart both servers cleanly

Write-Host "=== Cric Insights AI — Dev Restart ===" -ForegroundColor Cyan

# Kill anything on 5173 or 8002
$ports = @(5173, 8002)
foreach ($port in $ports) {
    $pids = (netstat -ano | Select-String ":$port\s" | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique)
    foreach ($pid in $pids) {
        if ($pid -match '^\d+$' -and $pid -ne '0') {
            try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}
Write-Host "Old processes killed" -ForegroundColor Yellow
Start-Sleep -Seconds 2

# Clear Vite cache
$viteCache = "c:\Users\1223505\Personal Apps\frontend\node_modules\.vite"
if (Test-Path $viteCache) {
    Remove-Item -Recurse -Force $viteCache
    Write-Host "Vite cache cleared" -ForegroundColor Yellow
}

# Start backend
Write-Host "Starting backend on :8002..." -ForegroundColor Green
Start-Process -FilePath "pwsh.exe" -ArgumentList @(
    "-NoLogo", "-NoProfile", "-Command",
    "cd 'c:/Users/1223505/Personal Apps'; .venv312/Scripts/uvicorn backend.src.main:app --host 127.0.0.1 --port 8002 --reload 2>&1 | Tee-Object -FilePath 'backend/uvicorn.log'"
) -WindowStyle Normal

Start-Sleep -Seconds 2

# Start frontend
Write-Host "Starting frontend on :5173..." -ForegroundColor Green
Start-Process -FilePath "pwsh.exe" -ArgumentList @(
    "-NoLogo", "-NoProfile", "-Command",
    "cd 'c:/Users/1223505/Personal Apps/frontend'; npm run dev"
) -WindowStyle Normal

Write-Host ""
Write-Host "Both servers starting in separate windows." -ForegroundColor Cyan
Write-Host "  Backend:  http://127.0.0.1:8002" -ForegroundColor White
Write-Host "  Frontend: http://127.0.0.1:5173" -ForegroundColor White
Write-Host ""
Write-Host "Wait ~40s for Parquet data to load, then open http://127.0.0.1:5173" -ForegroundColor Yellow
