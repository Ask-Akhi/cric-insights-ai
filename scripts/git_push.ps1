# scripts/git_push.ps1
# Invoked by the VS Code task "Git Push to GitHub"
# Commits any outstanding changes, then pushes to origin/master.

Set-Location "$PSScriptRoot\.."

Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor DarkGray
Write-Host "  🏏 Cricket Insights — Git Push        " -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor DarkGray

# ── 1. Show current state ─────────────────────────────────────────────────────
Write-Host "`n📋 Current log (last 6):" -ForegroundColor Cyan
git log --oneline -6

Write-Host "`n📂 Working-tree status:" -ForegroundColor Cyan
git status --short

# ── 2. Stage all changed tracked files ───────────────────────────────────────
Write-Host "`n➕ Staging changes..." -ForegroundColor Yellow
git add -u   # stage modifications/deletions to tracked files only

# Stage specific important files explicitly (covers new/untracked files)
$filesToAdd = @(
    # Backend — new + modified
    "backend/src/services/reranker.py",
    "backend/src/services/rag_service.py",
    "backend/src/routers/ask.py",
    "backend/src/routers/players.py",
    "backend/src/routers/matches.py",
    # Frontend — new components
    "frontend/src/components/Skeleton.tsx",
    "frontend/src/components/ThemeProvider.tsx",
    "frontend/src/components/RecentForm.tsx",
    "frontend/src/pages/MatchPredict.tsx",
    # Frontend — modified
    "frontend/src/components/ToolShell.tsx",
    "frontend/src/components/PlayerCharts.tsx",
    "frontend/src/components/PlayerSearchInput.tsx",
    "frontend/src/lib/api.ts",
    "frontend/src/index.css",
    "frontend/src/main.tsx",
    "frontend/src/pages/App.tsx",
    # Docs
    "MAC_IOS_SETUP.md"
)
foreach ($f in $filesToAdd) {
    if (Test-Path $f) { git add $f; Write-Host "   + $f" -ForegroundColor DarkGray }
}

# ── 3. Check if there's anything new to commit ───────────────────────────────
$staged = git diff --cached --name-only
if ($staged) {
    Write-Host "`n📝 Committing staged files:" -ForegroundColor Yellow
    $staged | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }

    $msg = "feat: reranker, RAG cache, /players/search, /matches/schedule, dark mode, skeletons, MatchPredict page, RecentForm widget, PlayerSearch autocomplete, latency/cache badges"
    git commit -m $msg
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Commit failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Committed." -ForegroundColor Green
} else {
    Write-Host "`nℹ️  Nothing new to commit — all changes already committed." -ForegroundColor DarkGray
}

# ── 4. Push ───────────────────────────────────────────────────────────────────
Write-Host "`n🚀 Pushing to origin/master..." -ForegroundColor Cyan
git push origin master 2>&1 | Tee-Object -Variable pushOut
$pushExit = $LASTEXITCODE

$pushOut | ForEach-Object { Write-Host $_ }

if ($pushExit -eq 0) {
    Write-Host "`n✅ Push successful! Railway will auto-deploy." -ForegroundColor Green
} else {
    Write-Host "`n❌ Push failed (exit $pushExit)." -ForegroundColor Red
    Write-Host "   Check your network / GitHub auth and try again." -ForegroundColor Yellow
    exit $pushExit
}

# ── 5. Save final log ─────────────────────────────────────────────────────────
git log --oneline -6 | Out-File -FilePath "scripts/git_log.txt" -Encoding utf8
git status --short    | Out-File -FilePath "scripts/git_status.txt" -Encoding utf8 -Append

Write-Host "`n📄 Updated scripts/git_log.txt" -ForegroundColor DarkGray
Write-Host ""
