@echo off
rem Baut die GUI als einzelne EXE nach dist\Konferenzplaner.exe
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
endlocal
