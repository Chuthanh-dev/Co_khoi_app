@echo off
echo =======================================================
echo   CLEANING UP STUCK BACKGROUND CHROME PROCESSES...
echo =======================================================
:: Kill only background Chrome processes using our automated profile
powershell -Command "Get-WmiObject Win32_Process -Filter \"name='chrome.exe'\" | Where-Object { $_.CommandLine -like '*chrome_profile*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
timeout /t 2 > nul

echo =======================================================
echo   STARTING GOOGLE CHROME IN AUTOMATION MODE (PORT 9222)
echo =======================================================
echo.

if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0chrome_profile" https://gemini.google.com
    exit
)

if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0chrome_profile" https://gemini.google.com
    exit
)

if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    start "" "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%~dp0chrome_profile" https://gemini.google.com
    exit
)

echo [ERROR] Google Chrome was not found on your system!
pause
