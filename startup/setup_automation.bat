@echo off
setlocal

:: Get the current directory (where the script is running)
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

:: Locate Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH. Please install Python.
    pause
    exit /b 1
)

:: Get Python Executable Path
for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%i"

echo [INFO] Detected Project Dir: %PROJECT_DIR%
echo [INFO] Detected Python: %PYTHON_EXE%

:: Create the run_indexer.bat file dynamically (Portable version)
echo @echo off > "%PROJECT_DIR%\run_indexer.bat"
echo cd /d "%%~dp0" >> "%PROJECT_DIR%\run_indexer.bat"
echo python ..\utility\indexer.py >> "%PROJECT_DIR%\run_indexer.bat"

echo [INFO] run_indexer.bat created.

:: OLLAMA MODEL SETUP
echo [INFO] Verifying AI Models...
echo Pulling base models (this may take time)...
call ollama pull functiongemma:270m
call ollama pull gemma3:4b

echo Creating Custom Function Model...
call ollama create functiongemma -f ..\utility\Modelfile

echo Creating Custom Chat Model (Jasper)...
call ollama create gemma3 -f ..\utility\ModelfileGemma3
echo [INFO] Models verified.

:: Create Scheduled Tasks
schtasks /create /f /tn "Jasper_Indexer_09AM" /tr "\"%PROJECT_DIR%\run_indexer.bat\"" /sc daily /st 09:00
schtasks /create /f /tn "Jasper_Indexer_01PM" /tr "\"%PROJECT_DIR%\run_indexer.bat\"" /sc daily /st 13:00

echo [INFO] Scheduled Tasks created.
echo [SUCCESS] Jasper initialization complete!
pause
