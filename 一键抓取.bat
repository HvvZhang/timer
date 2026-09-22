@echo off
chcp 936 >nul
setlocal
set "PYTHONIOENCODING=gbk:replace"
cd /d "%~dp0"
title 基金限购额度 - 手动抓取

set "ROOT=%~dp0"
set "PY=%ROOT%runtime\python\python.exe"

echo ================================================================
echo    手动抓取一次  +  生成当天日报
echo ================================================================
echo.

if not exist "%PY%" (
    echo [错误] 没有找到运行环境，请先运行「一键启动.bat」完成装配。
    echo.
    pause
    exit /b 1
)

pushd "%ROOT%fund_tracker"
"%PY%" run_fetch.py
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [!] 上面有 ERR 行，说明这几只没抓到（不会写入当天记录）。
"%PY%" make_report.py
popd

echo.
echo 日报已生成：fund_tracker\report\latest.html
if exist "%ROOT%fund_tracker\report\latest.html" start "" "%ROOT%fund_tracker\report\latest.html"
echo.
pause
exit /b 0
