Set-Location "c:\Users\1223505\Personal Apps"
Write-Host "Pushing to origin/master..." -ForegroundColor Cyan
$result = git push origin master 2>&1
Write-Host $result
$exitCode = $LASTEXITCODE
git log --oneline -4 > push_result.txt
git status >> push_result.txt
Add-Content push_result.txt "PUSH_EXIT_CODE=$exitCode"
Write-Host "Exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { 'Green' } else { 'Red' })
