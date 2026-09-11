@echo off
echo Downloading Arch Assistant 5GB bundle...
echo Repository: https://github.com/Wizzit-254/Arch-Assistant-Repo
echo.
set ZIPFILE=%TEMP%\Arch-Assistant-App.zip
powershell -Command "(New-Object Net.WebClient).DownloadFile('https://github.com/Wizzit-254/Arch-Assistant-Repo/releases/latest/download/Arch-Assistant-App.zip', '%ZIPFILE%')"
echo Extracting...
powershell -Command "Expand-Archive -Path '%ZIPFILE%' -DestinationPath '%LOCALAPPDATA%\ArchAssistant' -Force"
del '%ZIPFILE%'
echo.
echo Installation complete!
pause
