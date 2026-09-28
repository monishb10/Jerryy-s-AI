@echo off
setlocal enabledelayedexpansion

:: 1. Navigate to the project directory
cd /d "D:\Jerryy's AI"

:: 2. Counter for commits
set COUNT=0

:: 3. Loop through up to 7 untracked files (ignoring this script)
for /f "delims=" %%F in ('git ls-files --others --exclude-standard ^| findstr /v /i "daily_push.bat" ^| findstr /v /i "daily_push.sh"') do (
    if !COUNT! lss 7 (
        git add "%%F"
        git commit -m "Add %%~nxF"
        set /a COUNT+=1
    )
)

:: 4. Check if any files were committed
if %COUNT% equ 0 (
    echo [!] No untracked files left in D:\Jerryy's AI!
    pause
    exit /b 1
)

:: 5. Detect current branch and push
for /f "tokens=*" %%B in ('git branch --show-current') do set BRANCH=%%B
git push origin %BRANCH%

echo.
echo [OK] Success! Pushed %COUNT% files to branch '%BRANCH%'.
pause