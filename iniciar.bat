@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python nao encontrado. Instale em https://www.python.org/downloads/ ^(marque "Add to PATH"^).
    pause
    exit /b 1
)
python -m removedor_virus %*
pause
