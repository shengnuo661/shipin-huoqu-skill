"""Douyin provider using the H5 share page SSR payload."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from time import strftime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


PLATFORM = "douyin"

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

HEADERS = {
    "User-Agent": MOBILE_UA,
    "Referer": "https://www.iesdouyin.com/",
}


def supports(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(domain in host for domain in ("douyin.com", "iesdouyin.com"))


def fetch(url: str, output_root: Path, *, metadata_only: bool = False, **options) -> dict:
    allow_yt_dlp_fallback = options.get("allow_yt_dlp_fallback", True)
    cookies = options.get("cookies")
    no_chrome = options.get("no_chrome", False)
    provider_options = dict(options)
    provider_options.pop("allow_yt_dlp_fallback", None)
    provider_options.pop("cookies", None)
    provider_options.pop("no_chrome", None)
    errors = []

    # Route 1: 真实 Chrome 无头直链提取（全自动、无需登录态，优先）
    if not no_chrome:
        try:
            return _fetch_with_real_chrome(url, output_root, metadata_only=metadata_only)
        except Exception as exc:  # noqa: BLE001 - 任何失败都回退下一路由
            errors.append(f"real_chrome: {exc}")

    # Route 2: H5 分享页 SSR 解析（抖音改版前主路由，保留作兜底）
    try:
        return _fetch_h5(
            url,
            output_root,
            metadata_only=metadata_only,
            allow_yt_dlp_fallback=allow_yt_dlp_fallback,
            cookies=cookies,
            **provider_options,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"h5: {exc}")

    # Route 3: yt-dlp 最终兜底（需登录 cookie 或本机 Chrome 登录态）
    if allow_yt_dlp_fallback:
        try:
            return _fetch_with_ytdlp(
                url,
                output_root,
                metadata_only=metadata_only,
                primary_error=" | ".join(errors),
                cookies=cookies,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"ytdlp: {exc}")

    raise RuntimeError("All Douyin fetch routes failed: " + " | ".join(errors))


def _fetch_h5(
    url: str,
    output_root: Path,
    *,
    metadata_only: bool = False,
    allow_yt_dlp_fallback: bool = True,
    cookies: str | None = None,
    **options,
) -> dict:
    ratio = options.get("ratio") or "1080p"
    html, final_url = _download_text(url)
    router_data = _extract_router_data(html)
    item = _extract_item(router_data)
    video_info = item.get("video") or {}
    play_addr = video_info.get("play_addr") or {}
    play_url = _first(play_addr.get("url_list"))
    video_resource_id = _extract_video_resource_id(play_url) or play_addr.get("uri")
    aweme_id = str(item.get("aweme_id") or _extract_aweme_id(final_url) or "unknown")

    if not video_resource_id:
        raise RuntimeError("Could not find Douyin video resource ID in share page payload.")

    folder = output_root / f"douyin-{aweme_id}"
    folder.mkdir(parents=True, exist_ok=True)

    caption = item.get("desc") or ""
    post_caption_path = folder / "post_caption.txt"
    post_caption_path.write_text(caption, encoding="utf-8")

    metadata = _normalize_metadata(
        source_url=url,
        final_url=final_url,
        item=item,
        video_resource_id=video_resource_id,
        ratio=ratio,
    )

    video_path = None
    if not metadata_only:
        filename = _safe_filename(caption, aweme_id)
        video_path = folder / filename
        try:
            _download_binary(_build_nowm_url(video_resource_id, ratio), video_path)
            download_method = "douyin_h5_nowm"
            download_error = None
        except RuntimeError as exc:
            if not allow_yt_dlp_fallback:
                raise
            video_path = _download_with_ytdlp(url, folder, filename, cookies=cookies)
            download_method = "yt_dlp_fallback"
            download_error = str(exc)
        metadata["download"] = {
            "video_path": str(video_path),
            "method": download_method,
            "primary_error": download_error,
            "endpoint": "https://aweme.snssdk.com/aweme/v1/play/"
            if download_method == "douyin_h5_nowm"
            else None,
            "ratio": ratio,
        }
    else:
        metadata["download"] = {
            "video_path": None,
            "metadata_only": True,
            "ratio": ratio,
        }

    metadata_path = folder / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "platform": PLATFORM,
        "id": aweme_id,
        "output_dir": str(folder),
        "video_path": str(video_path) if video_path else None,
        "post_caption_path": str(post_caption_path),
        "caption_path": str(post_caption_path),
        "metadata_path": str(metadata_path),
        "post_caption": caption,
        "caption": caption,
        "author": metadata.get("author", {}).get("nickname"),
        "duration_seconds": metadata.get("video", {}).get("duration_seconds"),
        "resolution": metadata.get("video", {}).get("resolution"),
        "download_method": metadata.get("download", {}).get("method"),
    }


def _fetch_with_ytdlp(
    url: str,
    output_root: Path,
    *,
    metadata_only: bool,
    primary_error: str,
    cookies: str | None = None,
) -> dict:
    metadata = _extract_metadata_with_ytdlp(url, cookies=cookies)
    aweme_id = str(metadata.get("id") or _extract_aweme_id(metadata.get("webpage_url", "")) or "unknown")
    folder = output_root / f"douyin-{aweme_id}"
    folder.mkdir(parents=True, exist_ok=True)

    caption = metadata.get("description") or metadata.get("title") or ""
    post_caption_path = folder / "post_caption.txt"
    post_caption_path.write_text(caption, encoding="utf-8")

    video_path = None
    if not metadata_only:
        video_path = _download_with_ytdlp(url, folder, _safe_filename(caption, aweme_id), cookies=cookies)

    normalized = {
        "platform": PLATFORM,
        "source_url": url,
        "final_url": metadata.get("webpage_url"),
        "fetched_at": strftime("%Y-%m-%dT%H:%M:%S%z"),
        "id": aweme_id,
        "caption": caption,
        "author": {
            "nickname": metadata.get("uploader") or metadata.get("channel"),
            "unique_id": metadata.get("uploader_id"),
        },
        "video": {
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "resolution": _resolution(metadata.get("width"), metadata.get("height")),
            "duration_seconds": metadata.get("duration"),
        },
        "download": {
            "method": "yt_dlp_fallback",
            "video_path": str(video_path) if video_path else None,
            "metadata_only": metadata_only,
            "primary_error": primary_error,
        },
        "raw_ytdlp_metadata": metadata,
    }

    metadata_path = folder / "metadata.json"
    metadata_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "platform": PLATFORM,
        "id": aweme_id,
        "output_dir": str(folder),
        "video_path": str(video_path) if video_path else None,
        "post_caption_path": str(post_caption_path),
        "caption_path": str(post_caption_path),
        "metadata_path": str(metadata_path),
        "post_caption": caption,
        "caption": caption,
        "author": normalized.get("author", {}).get("nickname"),
        "duration_seconds": normalized.get("video", {}).get("duration_seconds"),
        "resolution": normalized.get("video", {}).get("resolution"),
        "download_method": "yt_dlp_fallback",
    }


def _download_text(url: str) -> tuple[str, str]:
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            return body, response.geturl()
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Failed to fetch Douyin share page: {exc}") from exc


def _download_binary(url: str, destination: Path) -> None:
    request = Request(url, headers=HEADERS)
    try:
        with urlopen(request, timeout=60) as response:
            suffix = destination.suffix or ".mp4"
            with tempfile.NamedTemporaryFile(
                "wb",
                delete=False,
                dir=str(destination.parent),
                suffix=suffix,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                shutil.copyfileobj(response, temp_file)
        temp_path.replace(destination)
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Failed to download Douyin video: {exc}") from exc


def _extract_metadata_with_ytdlp(url: str, cookies: str | None = None) -> dict:
    yt_dlp = _require_ytdlp()
    commands = []
    if cookies:
        commands.append(
            [yt_dlp, "--cookies", cookies, "--no-playlist", "--dump-single-json", url]
        )
    commands.extend([
        [yt_dlp, "--no-playlist", "--dump-single-json", url],
        [yt_dlp, "--cookies-from-browser", "chrome", "--no-playlist", "--dump-single-json", url],
    ])
    return json.loads(_run_first_successful(commands))


def _download_with_ytdlp(url: str, folder: Path, filename: str, cookies: str | None = None) -> Path:
    yt_dlp = _require_ytdlp()
    output_path = folder / filename
    base = [
        yt_dlp,
        "--no-playlist",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        str(output_path),
        url,
    ]
    commands = []
    if cookies:
        cookie_cmd = list(base)
        cookie_cmd.insert(1, "--cookies")
        cookie_cmd.insert(2, cookies)
        commands.append(cookie_cmd)
    commands.extend([
        base,
        [
            yt_dlp,
            "--cookies-from-browser",
            "chrome",
            "--no-playlist",
            "-f",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
            "-o",
            str(output_path),
            url,
        ],
    ])
    _run_first_successful(commands)
    if output_path.exists():
        return output_path

    matches = sorted(folder.glob(f"{output_path.stem}.*"))
    if matches:
        return matches[0]
    raise RuntimeError("yt-dlp reported success but no downloaded video file was found.")


def _run_first_successful(commands: list[list[str]]) -> str:
    errors = []
    for command in commands:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if completed.returncode == 0:
            return completed.stdout
        errors.append(completed.stderr.strip() or completed.stdout.strip())
    raise RuntimeError("yt-dlp fallback failed: " + " | ".join(errors))


def _require_ytdlp() -> str:
    yt_dlp = shutil.which("yt-dlp")
    if yt_dlp:
        return yt_dlp
    raise RuntimeError("yt-dlp fallback requested but yt-dlp is not installed or not on PATH.")


def _extract_router_data(html: str) -> dict:
    match = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\})</script>", html, re.S)
    if not match:
        raise RuntimeError("Could not find window._ROUTER_DATA in Douyin share page.")
    return json.loads(match.group(1))


def _extract_item(router_data: dict) -> dict:
    loader_data = (router_data.get("loaderData") or {})
    for key, value in loader_data.items():
        if "video" not in key or not isinstance(value, dict):
            continue
        video_info = value.get("videoInfoRes") or {}
        item_list = video_info.get("item_list") or []
        if item_list:
            return item_list[0]
    raise RuntimeError("Could not find Douyin item_list in router data.")


def _normalize_metadata(
    *,
    source_url: str,
    final_url: str,
    item: dict,
    video_resource_id: str,
    ratio: str,
) -> dict:
    author = item.get("author") or {}
    music = item.get("music") or {}
    video = item.get("video") or {}
    duration_ms = video.get("duration")
    width = video.get("width")
    height = video.get("height")

    return {
        "platform": PLATFORM,
        "source_url": source_url,
        "final_url": final_url,
        "fetched_at": strftime("%Y-%m-%dT%H:%M:%S%z"),
        "id": str(item.get("aweme_id") or ""),
        "group_id": str(item.get("group_id_str") or ""),
        "post_caption": item.get("desc") or "",
        "caption": item.get("desc") or "",
        "create_time": item.get("create_time"),
        "author": {
            "nickname": author.get("nickname"),
            "unique_id": author.get("unique_id"),
            "short_id": author.get("short_id"),
            "sec_uid": author.get("sec_uid"),
            "signature": author.get("signature"),
        },
        "music": {
            "id": music.get("mid"),
            "title": music.get("title"),
            "author": music.get("author"),
            "duration": music.get("duration"),
        },
        "video": {
            "resource_id": video_resource_id,
            "preferred_ratio": ratio,
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}" if width and height else None,
            "duration_ms": duration_ms,
            "duration_seconds": round(duration_ms / 1000, 3)
            if isinstance(duration_ms, (int, float))
            else None,
            "play_addr": video.get("play_addr"),
            "cover": video.get("cover"),
        },
        "statistics": item.get("statistics") or {},
        "risk_infos": item.get("risk_infos") or {},
        "hashtags": [
            extra.get("hashtag_name")
            for extra in (item.get("text_extra") or [])
            if extra.get("hashtag_name")
        ],
    }


def _build_nowm_url(video_resource_id: str, ratio: str) -> str:
    return (
        "https://aweme.snssdk.com/aweme/v1/play/"
        f"?video_id={video_resource_id}&ratio={ratio}&line=0"
    )


def _extract_video_resource_id(play_url: str | None) -> str | None:
    if not play_url:
        return None
    parsed = urlparse(play_url)
    return _first(parse_qs(parsed.query).get("video_id"))


def _extract_aweme_id(url: str) -> str | None:
    match = re.search(r"/(?:video|share/video)/(\d+)", url)
    return match.group(1) if match else None


def _first(value):
    if isinstance(value, list) and value:
        return value[0]
    return value


def _resolution(width, height) -> str | None:
    return f"{width}x{height}" if width and height else None


def _safe_filename(caption: str, aweme_id: str) -> str:
    stem = re.sub(r"\s+", " ", caption).strip()[:60] or "douyin-video"
    stem = re.sub(r'[\\/:*?"<>|#]+', "-", stem).strip(" .-")
    return f"{stem}-{aweme_id}.mp4"


# ---------------------------------------------------------------------------
# Route 1: 真实 Chrome 无头模式提取无水印直链（全自动，无需登录态）
# ---------------------------------------------------------------------------

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _resolve_chrome_path() -> str:
    """跨平台定位一个可用的真实 Chrome/Chromium 二进制。

    优先级：环境变量 DOUYIN_REAL_CHROME > 各平台常见安装路径。
    返回的路径会传给 Playwright 的 executable_path（而非 Playwright 自带的 Chromium），
    从而绕过抖音对自动化浏览器的识别。
    """
    env = os.environ.get("DOUYIN_REAL_CHROME")
    if env and Path(env).exists():
        return env
    home = Path.home()
    if sys.platform.startswith("win"):
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(home / "AppData/Local/Google/Chrome/Application/chrome.exe"),
            str(home / "AppData/Local/Microsoft/Edge/Application/msedge.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            str(home / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    else:  # linux
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            str(home / ".local/share/Chromium/chrome-linux/chrome"),
        ]
    for c in candidates:
        if Path(c).exists():
            return c
    raise RuntimeError(
        "No usable Chrome binary found. Install Chrome/Edge, or set the "
        "DOUYIN_REAL_CHROME environment variable to its executable path."
    )


def _fetch_with_real_chrome(url: str, output_root: Path, *, metadata_only: bool = False) -> dict:
    """用本机真实 Chrome 跑 --headless=new 打开抖音分享页，绕过机器人识别，
    从 aweme/v1/web/aweme/detail 接口拿无水印直链(play_addr) + 原版文案。"""
    from playwright.sync_api import sync_playwright

    chrome_path = _resolve_chrome_path()
    detail = None
    video_src = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=chrome_path,
            args=[
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--mute-audio",
                "--use-gl=swiftshader",
            ],
        )
        try:
            context = browser.new_context(
                user_agent=DESKTOP_UA,
                viewport={"width": 414, "height": 896},
                java_script_enabled=True,
            )
            context.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )
            page = context.new_page()
            captured = {}

            def on_response(response):
                u = response.url
                if "aweme/v1/web/aweme/detail" in u:
                    try:
                        captured["detail"] = response.json()
                    except Exception:
                        pass
                if "douyinvod.com" in u and "m3u8" not in u:
                    captured["video_src"] = u

            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            for _ in range(15):
                page.wait_for_timeout(2000)
                try:
                    src = page.evaluate(
                        "()=>{var v=document.querySelector('video');"
                        "return v?(v.currentSrc||v.src||''):'';}"
                    )
                    if src and "douyinvod" in src:
                        captured["video_src"] = src
                except Exception:
                    pass
                page.evaluate(
                    "document.querySelectorAll('video').forEach(v=>{"
                    "try{v.muted=true;v.play().catch(()=>{})}catch(e){}});"
                )
            detail = captured.get("detail")
            video_src = captured.get("video_src")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    play_addr, caption, aweme_id = _parse_chrome_detail(detail)
    src = play_addr or video_src
    if not src:
        raise RuntimeError("Chrome route captured no playable video URL.")

    aweme_id = aweme_id or _extract_aweme_id(url) or "unknown"
    folder = output_root / f"douyin-{aweme_id}"
    folder.mkdir(parents=True, exist_ok=True)

    caption = caption or ""
    post_caption_path = folder / "post_caption.txt"
    post_caption_path.write_text(caption, encoding="utf-8")

    video_path = None
    if not metadata_only:
        filename = _safe_filename(caption, aweme_id)
        video_path = folder / filename
        _download_binary_chrome(src, video_path)

    metadata = {
        "platform": PLATFORM,
        "source_url": url,
        "fetched_at": strftime("%Y-%m-%dT%H:%M:%S%z"),
        "id": aweme_id,
        "caption": caption,
        "post_caption": caption,
        "download": {
            "method": "douyin_real_chrome",
            "video_path": str(video_path) if video_path else None,
            "metadata_only": metadata_only,
            "watermark_free": bool(play_addr),
        },
    }
    metadata_path = folder / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "platform": PLATFORM,
        "id": aweme_id,
        "output_dir": str(folder),
        "video_path": str(video_path) if video_path else None,
        "post_caption_path": str(post_caption_path),
        "caption_path": str(post_caption_path),
        "metadata_path": str(metadata_path),
        "post_caption": caption,
        "caption": caption,
        "author": None,
        "duration_seconds": None,
        "resolution": None,
        "download_method": "douyin_real_chrome",
    }


def _parse_chrome_detail(detail):
    node = None
    if isinstance(detail, dict):
        if "aweme_detail" in detail:
            node = detail["aweme_detail"]
        elif "data" in detail and detail["data"]:
            node = detail["data"][0]
    if not node:
        return None, "", ""
    video = node.get("video", {})
    pa = video.get("play_addr", {}).get("url_list", [])
    desc = node.get("desc", "")
    aid = str(node.get("aweme_id", ""))
    return (pa[0] if pa else None), desc, aid


def _download_binary_chrome(url: str, destination: Path) -> None:
    request = Request(
        url,
        headers={"User-Agent": DESKTOP_UA, "Referer": "https://www.douyin.com/"},
    )
    try:
        with urlopen(request, timeout=180) as response, tempfile.NamedTemporaryFile(
            "wb",
            delete=False,
            dir=str(destination.parent),
            suffix=destination.suffix or ".mp4",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            shutil.copyfileobj(response, temp_file)
        temp_path.replace(destination)
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Failed to download via Chrome route: {exc}") from exc
