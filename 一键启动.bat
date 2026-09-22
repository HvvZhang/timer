@echo off
chcp 936 >nul
setlocal
set "PYTHONIOENCODING=gbk:replace"
cd /d "%~dp0"
title 基金限购额度盯盘

set "ROOT=%~dp0"
set "PY=%ROOT%runtime\python\python.exe"
set "PORT=5088"

echo ================================================================
echo    基金限购额度盯盘  -  一键启动
echo ================================================================
echo.

if not exist "%ROOT%fund_tracker\app.py" (
    echo [错误] 没有找到 fund_tracker\app.py
    echo        请把本文件放在 jijin 文件夹根目录下再运行。
    echo.
    pause
    exit /b 1
)

if exist "%PY%" goto :env_ok

echo [!] 没有找到便携运行环境，正在自动装配（约 1-2 分钟）...
echo.
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3 "%ROOT%setup_runtime.py"
    goto :env_check
)
python -c "import sys" >nul 2>&1
if not errorlevel 1 (
    python "%ROOT%setup_runtime.py"
    goto :env_check
)
echo     本机没有可用的 Python，无法自动装配。
echo     解决办法（二选一）：
echo       1) 把完整的 runtime 文件夹一起拷贝过来；
echo       2) 先安装 Python 3.9 以上版本，再重新运行本文件。
echo.
pause
exit /b 1

:env_check
if not exist "%PY%" (
    echo.
    echo [错误] 运行环境装配失败，请检查网络后重试。
    echo.
    pause
    exit /b 1
)

:env_ok
"%PY%" -c "import flask,requests" >nul 2>&1
if errorlevel 1 (
    echo [1/3] 补装依赖 flask / requests ...
    "%PY%" -m pip install --no-warn-script-location --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple flask requests
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败，请检查网络后重试。
        echo.
        pause
        exit /b 1
    )
) else (
    echo [1/3] 运行环境检查通过
)

netstat -ano | findstr ":5088" >nul 2>&1
if not errorlevel 1 (
    echo [2/3] 服务已经在运行，直接打开页面
    start "" "http://127.0.0.1:%PORT%"
    echo.
    echo        访问地址 : http://127.0.0.1:%PORT%
    echo        关闭服务 : 找到正在运行的那个窗口关掉即可
    echo.
    timeout /t 3 >nul
    exit /b 0
)

echo [2/3] 环境就绪
echo [3/3] 正在启动服务，3 秒后自动打开浏览器 ...
echo.
echo        访问地址 : http://127.0.0.1:%PORT%
echo        停止服务 : 直接关闭本窗口
echo.

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://127.0.0.1:%PORT%'"
"%PY%" "%ROOT%fund_tracker\app.py"

echo.
echo 服务已停止。
pause
exit /b 0
