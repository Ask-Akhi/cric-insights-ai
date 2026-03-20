@echo off
cd /d "c:\Users\1223505\Personal Apps"
echo === GIT LOG ===
git log --oneline -5
echo === GIT STATUS ===
git status --short
echo === GIT REMOTE ===
git remote -v
echo === STAGING start-dev.ps1 ===
git add start-dev.ps1
echo === COMMITTING ===
git commit -m "chore: add start-dev.ps1 convenience script" --allow-empty
echo === PUSHING ===
git push origin master
echo === DONE ===
