@echo off
setlocal
set "GH=C:\Program Files\GitHub CLI\gh.exe"

if not exist "%GH%" (
  echo [ERROR] gh.exe not found at "%GH%"
  pause
  exit /b 1
)

echo.
echo  === GitHub login ===
echo  1. Copy the 8-digit code shown below (example: ABCD-1234)
echo  2. Press Enter to open the browser
echo  3. Paste the code and click Authorize
echo.
echo  If asked:
echo    "What account?"        -^> GitHub.com
echo    "How to authenticate?" -^> Login with a web browser
echo.

"%GH%" auth login --web --hostname github.com --git-protocol https

echo.
echo  === status ===
"%GH%" auth status
echo.
pause
