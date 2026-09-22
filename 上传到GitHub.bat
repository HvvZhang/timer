@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title 上传到 GitHub

set "GIT=C:\Users\hvvzhang\Git\cmd\git.exe"
if not exist "%GIT%" set "GIT=git"

set "DEFAULT_REPO=https://github.com/HvvZhang/timer.git"

echo ================================================================
echo    把本项目推送到你的 GitHub 仓库
echo ================================================================
echo.
echo  目标仓库：%DEFAULT_REPO%
echo  （直接回车就用这个；想换仓库就把完整地址粘进来）
echo.
set /p REPO=仓库地址: 
if "%REPO%"=="" set "REPO=%DEFAULT_REPO%"

echo.
echo [1/3] 关联远程仓库
"%GIT%" remote remove origin >nul 2>&1
"%GIT%" remote add origin "%REPO%"
"%GIT%" remote -v
if errorlevel 1 goto :failed

echo.
echo [2/3] 提交本次改动
"%GIT%" add -A
"%GIT%" diff --cached --quiet
if errorlevel 1 (
    "%GIT%" commit -m "update: %date% %time%"
    if errorlevel 1 goto :failed
) else (
    echo      没有新改动，跳过
)

echo.
echo [3/3] 推送数据
echo      首次会弹出浏览器让你登录 GitHub，登录一次以后就不用了
"%GIT%" push -u origin main
if errorlevel 1 goto :failed

echo.
echo ================================================================
echo   推送成功！接下来在 GitHub 网页上做三件事
echo ================================================================
echo.
echo   1【必做】允许机器人写数据，否则定时抓取每次都会失败
echo      点 Settings -^> 左侧 Actions -^> General
echo      拉到最下面 Workflow permissions
echo      选 "Read and write permissions" -^> 点 Save
echo.
echo   2【必做】开启网页日报，手机也能看
echo      点 Settings -^> 左侧 Pages
echo      Source 选 "Deploy from a branch"
echo      分支选 main，目录选 /docs，点 Save
echo      一两分钟后打开：https://hvvzhang.github.io/timer/
echo.
echo   3【建议】立刻手动试跑一次
echo      点 Actions 标签页 -^> 左侧选「基金限购额度 · 每日抓取」
echo      -^>  右边 Run workflow  -^>  绿色按钮
echo.
echo   弄好之后，每天北京时间 09:35 和 21:30 自动抓两次，
echo   你的电脑关着、网页没开着，都不影响。
echo.
pause
exit /b 0

:failed
echo.
echo ================================================================
echo   出错了，常见原因
echo ================================================================
echo   - 仓库地址写错（要的是 https://github.com/用户名/仓库名.git）
echo   - 登录窗口被关掉了：重跑一次本文件，在浏览器里点允许
echo   - 远程仓库不是空的：建仓库时勾了 README，删掉那个文件再试
echo   - 网络连不上 GitHub：挂上代理再试
echo.
pause
exit /b 1
