Set-Location "c:\Users\1223505\Personal Apps"
Write-Host "=== LOG ===" -ForegroundColor Cyan
git log --oneline -5
Write-Host "=== STATUS ===" -ForegroundColor Cyan
git status --short
Write-Host "=== REMOTE ===" -ForegroundColor Cyan
git remote -v
Write-Host "=== ADDING start-dev.ps1 ===" -ForegroundColor Cyan
git add start-dev.ps1
Write-Host "=== COMMITTING ===" -ForegroundColor Cyan
git commit -m "chore: add start-dev.ps1 convenience script"
Write-Host "=== PUSHING ===" -ForegroundColor Cyan
git push origin master
Write-Host "=== DONE ===" -ForegroundColor Green
