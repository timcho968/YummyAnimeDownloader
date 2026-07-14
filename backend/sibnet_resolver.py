import re
import logging
import httpx
from .models import StreamUrl

log = logging.getLogger("downloader")

MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Mobile Safari/537.36"
)


async def resolve_sibnet_streams(iframe_url: str) -> list[StreamUrl]:
    videoid = _extract_videoid(iframe_url)
    if not videoid:
        raise ValueError(f"Cannot extract videoid from Sibnet URL: {iframe_url}")

    log.info(f"Sibnet: resolving videoid={videoid}")

    shell_url = f"https://video.sibnet.ru/shell.php?videoid={videoid}"
    referer = f"https://video.sibnet.ru/shell.php?videoid={videoid}"

    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=True,
        verify=False,
    ) as client:
        resp = await client.get(
            shell_url,
            headers={
                "User-Agent": MOBILE_UA,
                "Referer": referer,
            },
        )
        resp.raise_for_status()
        html = resp.text

    mp4_url = _extract_mp4(html)
    if not mp4_url:
        raise ValueError(f"Sibnet: no MP4 URL found in shell.php response")

    log.info(f"Sibnet: raw MP4 path: {mp4_url}")

    if mp4_url.startswith("/"):
        mp4_url = f"https://video.sibnet.ru{mp4_url}"

    final_url = _follow_redirects(mp4_url, referer)
    log.info(f"Sibnet: final URL: {final_url[:120]}...")

    return [StreamUrl(
        quality="720p",
        url=final_url,
        headers={
            "User-Agent": MOBILE_UA,
            "Referer": referer,
        },
    )]


def _extract_videoid(url: str) -> str | None:
    m = re.search(r"videoid=(\d+)", url)
    return m.group(1) if m else None


def _extract_mp4(html: str) -> str | None:
    patterns = [
        r"player\.src\(\s*['\"]([^'\"]+\.mp4)['\"]",
        r"src:\s*['\"]([^'\"]+\.mp4)['\"]",
        r"['\"](/v/[^'\"]+\.mp4)['\"]",
        r"(https?://[^'\"<>]+\.mp4[^'\"<>]*)",
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.group(1)
    return None


def _follow_redirects(url: str, referer: str) -> str:
    return url
