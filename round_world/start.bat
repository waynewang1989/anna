@echo off
chcp 65001 >nul
rem ---------------------------------------------------------------------------
rem  圆球秘境 · 寻宝 —— 一键启动脚本 (Windows)
rem  用法: start.bat [--selftest] [--weather rain] [-f]
rem ---------------------------------------------------------------------------
cd /d "%~dp0"
setlocal EnableDelayedExpansion

set "FORCE=0"
set "EXTRA="
:loop
if "%~1"=="" goto endloop
if /i "%~1"=="-f"        set "FORCE=1" & shift & goto loop
if /i "%~1"=="--force"   set "FORCE=1" & shift & goto loop
if /i "%~1"=="--selftest" set "RW_SELFTEST=1" & shift & goto loop
if /i "%~1"=="--weather"  set "RW_WEATHER=%~2" & shift & shift & goto loop
set "EXTRA=!EXTRA! %~1" & shift & goto loop
:endloop

where python >nul 2>&1 || (echo 错误: 未找到 python, 请先安装 Python 3.9+ 并勾选 Add to PATH & pause & exit /b 1)

if not exist ".venv\Scripts\python.exe" (
  echo ==^> 创建虚拟环境 .venv ...
  python -m venv .venv || (pause & exit /b 1)
)

set "STAMP=.venv\.requirements.stamp"
if "%FORCE%"=="0" if exist "%STAMP%" goto run
echo ==^> 安装依赖 (ursina / Pillow / numpy ...) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip || echo 提示: pip 自升级失败(可能离线), 继续...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
type nul > "%STAMP%"

:run
echo ==^> 启动游戏 (第三人称 · 蓝天白云) ...
".venv\Scripts\python.exe" game.py %EXTRA%
if errorlevel 1 pause
endlocal
