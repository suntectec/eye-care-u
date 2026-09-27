@echo off
chcp 65001 >nul
rem 一键打包护眼遮罩：dist\eye-care-u.exe（--onefile --noconsole）
rem venv 缺失时自动用系统 Python313（带 tkinter，托管 Python 没有）创建并装依赖。
rem 注意：必须用 "python -m PyInstaller" 形式——venv 若被整体搬移过，
rem       Scripts 下的入口 exe（pyinstaller.exe 等）内嵌旧路径会失效，-m 调用不受影响。
cd /d "%~dp0"

rem 程序运行中会锁住 exe 导致覆盖失败；且 taskkill 硬杀会跳过恢复色彩的
rem cleanup，屏幕染色残留——必须先托盘右键"退出"。
tasklist /FI "IMAGENAME eq eye-care-u.exe" | find /I "eye-care-u.exe" >nul
if not errorlevel 1 (
    echo [build] 护眼遮罩正在运行，请先右键托盘图标退出，再重新执行本脚本。
    exit /b 1
)

rem 系统 Python313 优先（带 tkinter）；找不到再退回 PATH 里的 python
set "PYEXE=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

if not exist ".build-venv\Scripts\python.exe" (
    echo [build] 未找到 .build-venv，正在用 %PYEXE% 创建...
    "%PYEXE%" -m venv .build-venv || (echo [build] venv 创建失败 & exit /b 1)
    ".build-venv\Scripts\python.exe" -m pip install pyinstaller pillow || (
        echo [build] 依赖安装失败 & exit /b 1)
)

rem logo.png 是唯一来源：打包前从它重生成多尺寸 logo.ico（exe 图标），
rem 打包资源再带上 logo.png（托盘图标/水印），exe 图标与托盘永远同图同色。
".build-venv\Scripts\python.exe" tools\make_ico.py || (
    echo [build] ico 生成失败 & exit /b 1)

".build-venv\Scripts\python.exe" -m PyInstaller --onefile --noconsole --name eye-care-u --icon assets/logo.ico --add-data "assets/logo.png;assets" eye_care_u.py
if errorlevel 1 (echo [build] 打包失败 & exit /b 1)

rem 打包后校验 exe 内嵌图标是否全尺寸（防回归到只有 16x16 的模糊图标）
".build-venv\Scripts\python.exe" tools\probe_icon_resources.py dist\eye-care-u.exe

echo [build] 完成: dist\eye-care-u.exe
