@echo off
REM ============================================================
REM  video-downloader 一键安装（Windows）
REM  在「其他 Windows 电脑」上复用本 skill 时运行一次即可。
REM  作用：创建/复用 WorkBuddy 隔离 venv，安装依赖，配置 ffmpeg。
REM ============================================================
setlocal
set "WB=%USERPROFILE%\.workbuddy"
set "VENV=%WB%\binaries\python\envs\default"
set "PY=%VENV%\Scripts\python.exe"
set "SKILL=%USERPROFILE%\.workbuddy\skills\video-downloader"

if not exist "%PY%" (
  echo [setup] 创建隔离 venv: %VENV%
  where py >nul 2>nul && py -m venv "%VENV%" || python -m venv "%VENV%"
) else (
  echo [setup] 复用已有 venv: %VENV%
)

echo [setup] 升级 pip + 安装核心依赖...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r "%SKILL%\requirements.txt"

echo [setup] （可选）口播转写 ASR 依赖未自动安装，需要时用：
echo        "%PY%" -m pip install -r "%SKILL%\requirements-extra.txt"

echo [setup] 配置 ffmpeg（供 whisper 转写使用）...
"%PY%" -m pip install imageio-ffmpeg
"%PY%" -c "import imageio_ffmpeg, shutil, os; src=imageio_ffmpeg.get_ffmpeg_exe(); dst=r'%VENV%\Scripts\ffmpeg.exe'; shutil.copyfile(src,dst); print('ffmpeg ->', dst)"

echo.
echo [setup] 完成！最后确认两件事：
echo   1) 本机已安装 Chrome 或 Edge（装了就能用，脚本会自动找到）；
echo      若浏览器路径特殊，请设置环境变量 DOUYIN_REAL_CHROME 指向其 exe。
echo   2) 下载默认落盘位置：环境变量 VIDEO_DOWNLOAD_DIR，未设置则 E:\视频下载。
echo.
echo [setup] 用法：%SKILL%\vd.bat ^<视频链接^>
endlocal
