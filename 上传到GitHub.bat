@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title 上传到 GitHub

set "GIT=C:\Users\hvvzhang\Git\cmd\git.exe"
if not exist "%GIT%" set "GIT=git"

echo ================================================================
echo    把本项目推送到你的 GitHub 仓库
echo ================================================================
echo.
echo  前置：先在 GitHub 网页上建好一个【空】仓库，
echo        建的时候不要勾选 Add a README / .gitignore / license。
echo.
echo  然后把你仓库的地址粘到下面（右键粘贴），例如：
echo        https://github.com/你的用户名/jijin.git
echo.
set /p REPO=仓库地址（直接回车 = 取消）: 
if "%REPO%"=="" (
    echo.
    echo [取消] 没有输入地址，什么都没做。
    pause
    exit /b 0
)

echo.
echo [1/2] 关联远程仓库
"%GIT%" remote remove origin >nul 2>&1
"%GIT%" remote add origin "%REPO%"
"%GIT%" remote -v
if errorlevel 1 goto :failed

echo.
echo [2/2] 推送数据
echo      首次会弹出浏览器让你登录 GitHub，登录一次以后就不用了
"%GIT%" push -u origin main
if errorlevel 1 goto :failed

echo.
echo ================================================================
echo   推送成功！接下来在 GitHub 网页上做两件事
echo ================================================================
echo.
echo   1) 开启网页日报（手机上也能看）
echo      Settings  -^>  Pages  -^>  Source 选 "Deploy from a branch"
echo      分支选 main，目录选 /docs，点 Save
echo      一两分钟后访问：https://你的用户名.github.io/仓库名/
echo.
echo   2) 立刻试跑一次抓取
echo      Actions 标签页  -^>  左侧选「基金限购额度 · 每日抓取」
echo      -^>  右侧 Run workflow  -^>  绿色按钮
echo.
echo   以后每天北京时间 09:35 和 21:30 自动跑，电脑关着也没关系。
echo.
pause
exit /b 0

:failed
echo.
echo ================================================================
echo   推送失败，常见原因
echo ================================================================
echo   - 仓库地址写错了（要是 .git 结尾的那种完整地址）
echo   - 登录窗口被关掉了：重跑一次本文件，在浏览器里点允许
echo   - 远程仓库不是空的：建仓库时勾了 README，删掉那个文件或换个空仓库
echo   - 网络连不上 GitHub：挂上代理再试
echo.
pause
exit /b 1
