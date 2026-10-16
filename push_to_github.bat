@echo off
cd /d "%~dp0"
echo Pushing commit to GitHub (origin main)...
"C:\Users\Sevtech\AppData\Local\GitHubDesktop\app-3.6.6\resources\app\git\cmd\git.exe" push origin main
echo.
pause
