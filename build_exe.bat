@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 用 PATH 上的 python; 也可把下面的 PY 改成你自己的解释器绝对路径
set "PY=python"

"%PY%" --version >nul 2>&1
if errorlevel 1 (
  echo [X] 未找到 python, 请先安装 Python 3.11+ 并加入 PATH
  pause
  exit /b 1
)

echo [1/3] 安装 pyinstaller ...
"%PY%" -m pip install --quiet pyinstaller
if errorlevel 1 ( echo [X] pyinstaller 安装失败 & pause & exit /b 1 )

echo [2/3] 打包 exe ...
"%PY%" -m PyInstaller --noconfirm --onefile --windowed --name "ceramic-agent-gui" gui_launcher.py
if errorlevel 1 ( echo [X] 打包失败, 看上面报错 & pause & exit /b 1 )

echo [3/3] 完成, exe 在: %~dp0dist\ceramic-agent-gui.exe
echo 把它复制到本仓库根目录(与 store/ learning/ 同级)后双击运行
pause
