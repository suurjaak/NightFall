:: Creates NSIS setup file for executable in current directory named 
:: %parentdirname%_%conf.Version%[_x64].exe, or filename given in argument.
:: Processor architecture is determined from OS environment.
::
:: @author    Erki Suurjaak
:: @created   21.08.2019
:: @modified  05.04.2022
@echo off
:: Expand variables at execution time rather than at parse time
setlocal EnableDelayedExpansion
set INITIAL_DIR=%CD%
cd %0\..
set SETUPDIR=%CD%

cd ..
for %%f in ("%CD%") do set NAME=%%~nxf

set SUFFIX64=
for /f %%i in ('python -c "import struct; print(struct.calcsize(""P"") * 8)"') do set ADDRSIZE=%%i
if "%ADDRSIZE%" equ "64" set SUFFIX64=_x64

if [%1] == [] (
    cd src
    for /f %%I in ('python -c "from nightfall import conf; print(conf.Version)"') do set VERSION=%%I
    set EXEFILE=%INITIAL_DIR%\%NAME%_!VERSION!%SUFFIX64%.exe
) else (
    for /f "tokens=2 delims=_ " %%a in ("%~n1") do set VERSION=%%a
    echo "VERSION2 = %VERSION%."
    set EXEFILE=%INITIAL_DIR%\%1
)



if not exist "%EXEFILE%" echo %EXEFILE% missing. && goto :END
set NSISDIR=C:\Program Files (x86)\Nullsoft Scriptable Install System
if not exist "%NSISDIR%" set NSISDIR=C:\Program Files\Nullsoft Scriptable Install System
if not exist "%NSISDIR%" set NSISDIR=C:\Program Files (x86)\NSIS
if not exist "%NSISDIR%" set NSISDIR=C:\Program Files\NSIS
if not exist "%NSISDIR%\makensis.exe" echo NSIS not found. && goto :END

echo Creating installer for %NAME% %VERSION%%SUFFIX64%.
cd %SETUPDIR%
set DESTFILE=%NAME%_%VERSION%%SUFFIX64%_setup.exe
if exist "%DESTFILE%" echo Removing previous %DESTFILE%. & del "%DESTFILE%"
if exist %NAME%.exe del %NAME%.exe
copy /V "%EXEFILE%" %NAME%.exe > NUL 2>&1
"%NSISDIR%\makensis.exe" /DVERSION=%VERSION% /DSUFFIX64=%SUFFIX64% "%SETUPDIR%\exe_setup.nsi"
del %NAME%.exe > NUL 2>&1
if exist "%DESTFILE%" echo. & echo Successfully created %NAME% source distribution %DESTFILE%.
move "%DESTFILE%" "%INITIAL_DIR%" > NUL 2>&1

:END
cd "%INITIAL_DIR%"
