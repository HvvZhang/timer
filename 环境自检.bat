@echo off
chcp 936 >nul
setlocal
set "PYTHONIOENCODING=gbk:replace"
cd /d "%~dp0"
title 运行环境自检

set "ROOT=%~dp0"
set "PY=%ROOT%runtime\python\python.exe"

echo ================================================================
echo    运行环境自检
echo ================================================================
echo.

echo [1] 便携运行环境
if exist "%PY%" (
    "%PY%" -c "import sys;print('      路径 : '+sys.executable);print('      版本 : '+sys.version.split()[0])"
    "%PY%" -c "import flask,requests;print('      flask    '+flask.__version__);print('      requests '+requests.__version__)" 2>nul
    if errorlevel 1 echo      [X] 依赖不完整，请运行「一键启动.bat」自动补装
) else (
    echo      [X] 缺失 runtime\python\python.exe
    echo          请运行「一键启动.bat」，会尝试自动装配
)
echo.

echo [2] 基金清单
if exist "%ROOT%fund_tracker\funds.txt" (
    "%PY%" -c "import sys,collections;sys.path.append(r'%ROOT%fund_tracker');import fetcher;fs=fetcher.load_funds();c=collections.Counter(f['category'] for f in fs);print('      共 '+str(len(fs))+' 只');print('      '+' | '.join(k+' '+str(c[k])+' 只' for k in sorted(c,key=fetcher.category_rank)))"
) else (
    echo      [X] 缺失 fund_tracker\funds.txt
)
echo.

echo [3] 本地数据库
if exist "%ROOT%fund_tracker\data\funds.db" (
    "%PY%" -c "import sqlite3;p=r'%ROOT%fund_tracker\data\funds.db';c=sqlite3.connect(p);r=c.execute('SELECT COUNT(DISTINCT snap_date),MIN(snap_date),MAX(snap_date) FROM daily_record').fetchone();n=c.execute('SELECT COUNT(*) FROM daily_record').fetchone()[0];print('      记录 '+str(n)+' 条，覆盖 '+str(r[0])+' 个日期（'+str(r[1])+' ~ '+str(r[2])+'）')"
) else (
    echo      [!] 还没有数据库，运行一次抓取即可生成
)
echo.

echo [4] 端口 5088
netstat -ano | findstr ":5088" >nul 2>&1
if errorlevel 1 (
    echo      空闲（服务未启动）
) else (
    echo      已被占用 —— 说明网页服务正在运行
)
echo.

echo [5] 数据可携带性
echo      本目录整体拷贝到别的电脑即可使用，
echo      运行环境在 runtime\ 里，不依赖 C 盘的 Python。
echo.
pause
exit /b 0
