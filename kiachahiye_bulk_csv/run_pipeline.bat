@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title KiaChahiye Bulk CSV Generator
cd /d "%~dp0"

rem ============================================================
rem  KiaChahiye Bulk CSV Generator - launcher
rem    run_pipeline.bat                          (default sheet: data\input\Products.csv)
rem    run_pipeline.bat "D:\path\MY SHEET.csv"   (any sheet)
rem    run_pipeline.bat --no-tests               (skip the test stage)
rem  Or drag and drop a CSV onto this file.
rem  All the screen work happens in run_ui.py (Python only, nothing to install).
rem ============================================================

set "PY=python"
%PY% --version >nul 2>nul
if errorlevel 1 set "PY=py"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo   [ERROR] Python was not found.
  echo           Install Python 3.10+ from python.org and tick "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

set "PKG=%~dp0"
if exist "%~dp0kiachahiye_bulk_csv\run_ui.py" set "PKG=%~dp0kiachahiye_bulk_csv\"
if not exist "%PKG%run_ui.py" (
  echo.
  echo   [ERROR] run_ui.py not found next to this file.
  echo.
  pause
  exit /b 1
)

pushd "%PKG%"
%PY% run_ui.py %*
set "RC=%ERRORLEVEL%"
popd

endlocal & exit /b %RC%
