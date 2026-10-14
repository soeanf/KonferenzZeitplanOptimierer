@echo off
rem Baut GUI und CLI als einzelne EXE-Dateien nach dist\
rem   dist\Konferenzplaner.exe      (GUI)
rem   dist\Konferenzplaner-cli.exe  (Kommandozeile)
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo .venv fehlt. Bitte zuerst die Umgebung einrichten, siehe README.
    exit /b 1
)
.venv\Scripts\python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Konferenzplaner ^
    --collect-all ortools ^
    --collect-data sv_ttk ^
    run_gui.py
if errorlevel 1 exit /b 1
.venv\Scripts\python -m PyInstaller --noconfirm --onefile --console ^
    --name Konferenzplaner-cli ^
    --collect-all ortools ^
    run_cli.py
endlocal
