@echo off
chcp 65001 >nul
cd /d "%~dp0"

set VENV=.venv312
set PY=%VENV%\Scripts\python.exe

echo [1/3] 准备 Python 3.12 打包环境...
where py >nul 2>&1
if errorlevel 1 (
    echo 未找到 py 启动器，请先安装 Python 3.12
    pause
    exit /b 1
)
py -3.12 -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo 未找到 Python 3.12。可执行: winget install Python.Python.3.12
    pause
    exit /b 1
)

if not exist "%PY%" (
    echo 创建虚拟环境 %VENV% ...
    py -3.12 -m venv "%VENV%"
    if errorlevel 1 (
        echo 创建虚拟环境失败
        pause
        exit /b 1
    )
)

echo 安装/更新打包依赖...
"%PY%" -m pip install -q -U pip
"%PY%" -m pip install -q -r requirements-build.txt
if errorlevel 1 (
    echo 依赖安装失败
    pause
    exit /b 1
)

echo [2/3] 开始打包（单文件 onefile，Python 3.12）...
"%PY%" -m PyInstaller WarframePrimeHelper.spec --noconfirm --clean
if errorlevel 1 (
    echo 打包失败
    pause
    exit /b 1
)

echo [3/3] 完成
echo.
echo 可执行文件: dist\Warframe开核桃助手.exe
echo 说明: config.json、价格缓存、sound\ 会写在 exe 同目录
echo.
pause
