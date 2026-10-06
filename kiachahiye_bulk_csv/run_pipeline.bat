@echo off
setlocal enabledelayedexpansion
title KiaChahiye Bulk CSV Generator - Runner
cd /d "%~dp0"

rem ============================================================
rem  KiaChahiye Bulk CSV Generator - Runner
rem  Chalane ka tareeqa:
rem    run_pipeline.bat                          (default sheet)
rem    run_pipeline.bat "D:\path\MY SHEET.csv"   (koi bhi sheet)
rem  Ya CSV file ko is bat ke icon par DRAG AND DROP kar dein.
rem ============================================================

rem ---- 1) Python dhoondein ----------------------------------------------------
set "PY=python"
%PY% --version >nul 2>nul
if errorlevel 1 set "PY=python3"
%PY% --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo [ERROR] Python nahi mila.
  echo         python.org se Python install karein aur install ke waqt
  echo         "Add Python to PATH" ka box tick karein.
  echo.
  pause
  exit /b 1
)

rem ---- 2) Program folder khud dhoond lein -------------------------------------
rem  Yeh bat do shaklon mein chalti hai:
rem    (a)  run_pipeline.bat  +  kiachahiye_bulk_csv\main.py ...
rem    (b)  run_pipeline.bat  +  main.py ...            (sab ek hi folder mein)
set "HERE=%~dp0"
set "PKG=%HERE%kiachahiye_bulk_csv"
if not exist "%PKG%\main.py" set "PKG=%HERE:~0,-1%"
if not exist "%PKG%\main.py" (
  echo.
  echo [ERROR] main.py nahi mila.
  echo         Is bat ko us folder mein rakhein jahan main.py hai, ya us ke
  echo         sath wala "kiachahiye_bulk_csv" folder rakhein.
  echo.
  pause
  exit /b 1
)

rem ---- 3) Default sheet ya aap ki di hui sheet? -------------------------------
set "CUSTOM=0"
set "OUTDIR=%PKG%\data\output"
if not "%~1"=="" (
  set "CUSTOM=1"
  for %%F in ("%~1") do set "RUN=%%~nF"
  set "OUTDIR=%PKG%\data\output\!RUN!"
)

echo ===================================================
echo   KiaChahiye Bulk CSV Generator - Runner
echo ===================================================
echo [INFO] Python        : %PY%
echo [INFO] Program folder: %PKG%
if "%CUSTOM%"=="1" (
  echo [INFO] Sheet         : "%~1"
  echo [INFO] Output folder : %OUTDIR%\
  echo [INFO] Default wali files data\output\ mein waise hi safe rahengi.
) else (
  echo [INFO] Sheet         : data\input\READY FIRST STEP 1 CSV.csv
  echo [INFO] Output folder : %OUTDIR%\
)

pushd "%PKG%"

echo.
echo [1/4] Running tests...
if not exist "%PKG%\tests" (
  echo [WARN] tests folder nahi mila - test step skip kar rahe hain.
  goto :aftertests
)
%PY% -c "import pytest" >nul 2>nul
if errorlevel 1 (
  echo [WARN] pytest install nahi hai - test step skip kar rahe hain.
  echo        Install ke liye:  %PY% -m pip install pytest
  goto :aftertests
)
%PY% -m pytest tests -q
if errorlevel 1 (
  echo.
  echo [ERROR] Tests fail hue - pipeline rok diya gaya hai.
  echo         Koi output file change nahi hui.
  popd
  pause
  exit /b 1
)

:aftertests
echo.
echo [2/4] Running the pipeline...
if "%CUSTOM%"=="0" (
  %PY% main.py
) else (
  %PY% main.py --input "%~1" --digi "%OUTDIR%\digi\digimall_bulk_import.csv" --alfa "%OUTDIR%\alfa\alfa_bulk_import.csv" --qc "%OUTDIR%\qc_report.csv" --sample-titles "%OUTDIR%\title_review_sample.csv"
)
if errorlevel 1 (
  echo.
  echo [ERROR] Pipeline fail hui - upar wala error message dekhein.
  echo         Sheet ka path aur columns check karein.
  popd
  pause
  exit /b 1
)

echo.
echo [3/4] Running audit verification...
if "%CUSTOM%"=="0" (
  %PY% audit.py --evidence "data\output\row_check.csv"
) else (
  %PY% audit.py --input "%~1" --digi "%OUTDIR%\digi\digimall_bulk_import.csv" --alfa "%OUTDIR%\alfa\alfa_bulk_import.csv" --qc "%OUTDIR%\qc_report.csv" --evidence "%OUTDIR%\row_check.csv"
)
if errorlevel 1 (
  echo.
  echo [WARN] AUDIT FAIL hua - upar wali FAIL lines dekhein.
  echo        Jab tak PASS na ho, yeh files upload NA karein.
) else (
  echo [OK] Audit pass.
)

echo.
echo [4/4] Building the weak-Description worklist (advisory, never blocks)...
if "%CUSTOM%"=="0" (
  %PY% thin_report.py
) else (
  %PY% thin_report.py --input "%~1" --digi "%OUTDIR%\digi\digimall_bulk_import.csv" --qc "%OUTDIR%\qc_report.csv" --out "%OUTDIR%\thin_descriptions.csv"
)

popd
echo.
echo ===================================================
echo   Done. Upload karne wali do files:
if "%CUSTOM%"=="0" (
  echo     %PKG%\data\output\digi\digimall_bulk_import.csv
  echo     %PKG%\data\output\alfa\alfa_bulk_import.csv
) else (
  echo     %OUTDIR%\digi\digimall_bulk_import.csv
  echo     %OUTDIR%\alfa\alfa_bulk_import.csv
)
echo.
echo   Audit ka nateeja upar dekhein - hona chahiye: checks 45 ^| passed 45 ^| failed 0
echo   Description pehle saaf karni ho to chala dein: python clean_descriptions.py
echo ===================================================
endlocal
echo.
pause
