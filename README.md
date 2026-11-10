# video-downloader（抖音无水印视频下载 skill）

一个 WorkBuddy skill：**只给抖音分享链接，全自动下载无水印视频 + 原版文案 + 元数据**，无需手动登录、无需导出 cookie。

## 它能做什么

- 输入抖音分享短链（`v.douyin.com/xxx`），输出：
  - 无水印视频（取自抖音 `play_addr` 源，非带水印的 `playwm`）
  - 原发布文案 `post_caption.txt`
  - 元数据 `metadata.json`
  - （可选）口播逐字稿 `transcript*.json`（需装 ASR 依赖）
- 路由顺序：**真实 Chrome 无头直链**（首选，全自动）→ H5 分享页解析（兜底）→ yt-dlp（需 cookie 兜底）

## 运行必要条件（三样）

| # | 东西 | 说明 |
|---|------|------|
| 1 | **skill 代码** | 本仓库，纯文本，直接复制 |
| 2 | **Python 隔离环境 + 依赖** | 见 `requirements.txt`，一键 `setup` 安装 |
| 3 | **一个真实 Chrome / Edge 浏览器** | 抖音反爬只认「真实浏览器」，脚本用 `--headless=new` 调它 |

> 关键点：**不是 Playwright 自带的 Chromium**（会被抖音识别成机器人），
> 而是本机装的真实 Chrome/Edge。脚本通过 `DOUYIN_REAL_CHROME` 或默认路径自动找到它。

## 安装（其他电脑复用）

### Windows
```bat
rem 1. 把本仓库放到： C:\Users\<用户名>\.workbuddy\skills\video-downloader\
rem 2. 双击运行：
setup.bat
```

### macOS / Linux
```bash
# 1. 把本仓库放到： ~/.workbuddy/skills/video-downloader/
# 2. 运行：
bash setup.sh
```

`setup` 会：创建/复用 WorkBuddy 隔离 venv → `pip install -r requirements.txt` → 配好 ffmpeg。
**核心依赖不含 torch，安装很快。** 若要口播转写，再装可选依赖：
```bat
"%~USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m pip install -r requirements-extra.txt
```

## 使用

Windows：
```bat
vd.bat https://v.douyin.com/xxxx/
vd.bat https://v.douyin.com/xxxx/ D:\my_videos   # 指定输出目录
vd.bat https://v.douyin.com/xxxx/ --asr none      # 只下视频+文案，不转写
```
macOS / Linux：
```bash
bash vd.sh https://v.douyin.com/xxxx/
```

## 两个环境变量

| 变量 | 作用 | 默认 |
|------|------|------|
| `DOUYIN_REAL_CHROME` | 指定浏览器 exe 路径（路径特殊时必设） | 各平台常见路径自动探测 |
| `VIDEO_DOWNLOAD_DIR` | 视频下载根目录 | `E:\视频下载`（未设置时；非 Windows 建议改设 `~/视频下载`） |

## 常见问题

- **`No usable Chrome binary found`** → 没装浏览器或路径不在默认列表。装 Chrome，或设 `DOUYIN_REAL_CHROME`。
- **抖音返回空 / 403** → 抖音偶发升级反爬。真实 Chrome 路由通常不受影响；若失效，加 `--no-chrome` 回退 yt-dlp（需登录 cookie）。
- **转写缺 ffmpeg** → 重跑 `setup` 会补 ffmpeg；或加 `--asr none` 只下视频。
- **非 Windows 默认目录是 `E:\视频下载`** → 设 `VIDEO_DOWNLOAD_DIR` 环境变量覆盖即可。

## 合规提醒

下载仅供**拆解 / 口播结构 / 人设语气**参考；原样搬运发布既侵权又会被平台限流。
