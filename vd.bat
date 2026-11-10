@echo off
REM ============================================================
REM  video-downloader 启动脚本（Windows）
REM  作用：把隔离 Python 环境的工具加入 PATH，再调用 skill
REM  用法：vd.bat <视频链接> [输出目录] [额外参数...]
REM  示例：vd.bat https://v.douyin.com/xxx ./downloads
REM ============================================================
setlocal

REM 隔离 Python 环境目录（含 yt-dlp / whisper / ffmpeg）
set "VENV=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts"

REM 将工具目录加入 PATH 最前，确保 which() 能命中
set "PATH=%VENV%;%PATH%"

REM skill 脚本目录
set "SKILL_DIR=%USERPROFILE%\.workbuddy\skills\video-downloader\scripts"

REM 调用 python 执行 skill 入口
"%VENV%\python.exe" "%SKILL_DIR%\download_video.py" %*

endlocal
