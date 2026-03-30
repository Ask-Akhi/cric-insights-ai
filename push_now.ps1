Set-Location "c:\Users\1223505\Personal Apps"

# 1. Remove stray tracked files
git rm --cached 'ers1223505Personal Apps && python -c ' 2>$null
git rm --cached test_split.mjs 2>$null

# 2. Stage all session changes
git add -u
git add .gitignore
git add scripts/git_push.ps1
git add scripts/do_commit_push.ps1
git add frontend/src/components/ToolShell.tsx
git add frontend/src/components/LiveScoreTicker.tsx
git add frontend/src/pages/PlayerCompare.tsx
git add backend/src/routers/players.py

# 3. Show what will be committed
Write-Host "`n=== Files to commit ===" -ForegroundColor Cyan
git diff --cached --name-only

# 4. Commit (if anything staged)
$staged = git diff --cached --name-only
if ($staged) {
    git commit -m "fix: user-friendly badges, CSS scroll, table split guard, player aliases

- ToolShell: ModeBadge shows Deep Analysis / Quick Answer / Web-grounded (not LangGraph/Direct LLM)
- ToolShell: data-source badges show Ball-by-ball data / Live web search / AI knowledge
- ToolShell: CSS max-height expand/collapse (replaces framer-motion height animation)
- ToolShell: CSS transition-transform on chevron (replaces motion.span rotate)
- ToolShell: never split if answer contains any markdown table row
- ToolShell: Preparing your insights... + cricket-friendly thinking steps
- players.py: 25+ new aliases (Sanju Samson, Yashasvi Jaiswal, Ruturaj Gaikwad, etc.)
- players.py: _fuzzy_resolve() surname-based fallback for unmatched names
- PlayerCompare: format param fix; amber not-found card instead of red error
- LiveScoreTicker: 90s poll interval, pause on hidden tab, refetch on focus
- .gitignore: test_split.mjs, patch_spm.py, ers1223505* added to ignore"
    Write-Host "Committed!" -ForegroundColor Green
} else {
    Write-Host "Nothing new to commit." -ForegroundColor DarkGray
}

# 5. Push
Write-Host "`n=== Pushing to GitHub ===" -ForegroundColor Cyan
git push origin master
$exitCode = $LASTEXITCODE

# 6. Save result
git log --oneline -6 | Out-File push_result.txt -Encoding utf8
git status --short   | Out-File push_result.txt -Encoding utf8 -Append
Add-Content push_result.txt "PUSH_EXIT_CODE=$exitCode"

Write-Host "Exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { 'Green' } else { 'Red' })
git log --oneline -5
