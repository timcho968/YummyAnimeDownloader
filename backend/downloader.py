import os
import re
import subprocess
import tempfile
import logging
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

log = logging.getLogger("downloader")

logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def download_video(
    url: str,
    output_path: str,
    referer: str = "https://yummyani.me/",
    cookies: Optional[dict[str, str]] = None,
    extra_headers: Optional[dict[str, str]] = None,
    progress_callback: Optional[Callable] = None,
) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    log.info(f"Starting download: {output_path}")
    log.info(f"URL: {url[:120]}...")
    log.info(f"Referer: {referer}")
    log.info(f"Cookies: {list(cookies.keys()) if cookies else 'none'}")
    log.info(f"Extra headers: {list(extra_headers.keys()) if extra_headers else 'none'}")

    if progress_callback:
        progress_callback({
            "status": "downloading",
            "percent": 0,
            "filename": os.path.basename(output_path),
        })

    headers = {**HEADERS, "Referer": referer, "Origin": "https://yummyani.me"}
    if extra_headers:
        headers.update(extra_headers)
    cookie_dict = cookies or {}

    log.info("Downloading via httpx (parallel segments)...")

    try:
        return _download_httpx(url, output_path, headers, cookie_dict, progress_callback)
    except Exception as e:
        log.warning(f"httpx failed ({e}), falling back to ffmpeg")
        return _download_ffmpeg(url, output_path, referer, cookie_dict, extra_headers or {}, progress_callback)


def _download_ffmpeg(url, output_path, referer, cookies, extra_headers, progress_callback):
    cmd = [
        "ffmpeg", "-y",
        "-referer", referer,
        "-user_agent", (extra_headers or {}).get("User-Agent", HEADERS["User-Agent"]),
    ]

    http_headers = f"Cookie: {'; '.join(f'{k}={v}' for k, v in cookies.items())}\r\n" if cookies else ""
    http_headers += f"Origin: https://yummyani.me\r\n"
    http_headers += f"Accept: */*\r\n"
    for k, v in (extra_headers or {}).items():
        if k.lower() != "user-agent":
            http_headers += f"{k}: {v}\r\n"
    if http_headers:
        cmd.extend(["-headers", http_headers])

    cmd.extend([
        "-i", url,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path,
    ])

    log.info("Trying ffmpeg direct download (timeout: 120s)...")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise RuntimeError("ffmpeg timed out after 120s")

    duration = 0.0
    for line in stderr.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        log.debug(f"ffmpeg: {stripped}")

        if duration == 0:
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)", line)
            if dur_match:
                dh, dm, ds = dur_match.groups()
                duration = int(dh) * 3600 + int(dm) * 60 + int(ds)
                log.info(f"Stream duration: {duration}s")

        time_match = re.search(r"time=\s*(\d+):(\d+):(\d+)\.(\d+)", line)
        if time_match and progress_callback:
            h, m, s, cs = time_match.groups()
            current = int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100
            if current > 0 and duration > 0:
                percent = min(99, (current / duration) * 100)
                progress_callback({
                    "status": "downloading",
                    "percent": round(percent, 1),
                    "filename": os.path.basename(output_path),
                })

    if process.returncode != 0:
        if "403" in stderr:
            raise RuntimeError(f"ffmpeg failed with 403 Forbidden")
        raise RuntimeError(f"ffmpeg failed (code {process.returncode})")

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("ffmpeg produced empty or missing file")

    file_size = os.path.getsize(output_path)
    log.info(f"Download complete via ffmpeg: {output_path} ({file_size} bytes)")
    if progress_callback:
        progress_callback({
            "status": "done",
            "percent": 100,
            "filename": os.path.basename(output_path),
        })
    return output_path


def _download_httpx(url, output_path, headers, cookies, progress_callback):
    PARALLEL_WORKERS = 8
    log.info("Starting httpx segment download (parallel)...")

    limits = httpx.Limits(max_connections=PARALLEL_WORKERS, max_keepalive_connections=4)
    client = httpx.Client(headers=headers, cookies=cookies or {}, follow_redirects=True, timeout=30, verify=False, limits=limits)
    tmpdir = None
    concat_file = None
    segment_files = []

    try:
        resp = client.get(url)
        resp.raise_for_status()
        master_content = resp.text
        master_url = str(resp.url)

        variant_url = parse_best_variant(master_content, master_url)

        if variant_url == master_url:
            variant_content = master_content
        else:
            log.info(f"Best variant: {variant_url[:120]}...")
            resp2 = client.get(variant_url)
            resp2.raise_for_status()
            variant_content = resp2.text
            variant_url = str(resp2.url)

        segments = parse_segments(variant_content, variant_url)
        log.info(f"Found {len(segments)} segments, downloading with {PARALLEL_WORKERS} workers")

        if not segments:
            raise RuntimeError("No segments found in playlist")

        tmpdir = tempfile.mkdtemp(prefix="yummy_dl_")
        concat_file = os.path.join(tmpdir, "concat.txt")
        segment_files = [None] * len(segments)
        completed = 0

        def download_segment(args):
            i, seg_url = args
            seg_path = os.path.join(tmpdir, f"seg_{i:05d}.ts")
            last_err = None
            for attempt in range(3):
                try:
                    resp = client.get(seg_url)
                    resp.raise_for_status()
                    with open(seg_path, "wb") as f:
                        f.write(resp.content)
                    return i, seg_path
                except Exception as e:
                    last_err = e
                    if attempt < 2:
                        import time
                        time.sleep(1 * (attempt + 1))
            raise last_err

        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as pool:
            futures = {pool.submit(download_segment, (i, url)): i for i, url in enumerate(segments)}
            for future in as_completed(futures):
                i, seg_path = future.result()
                segment_files[i] = seg_path
                completed += 1

                if progress_callback and completed % 10 == 0:
                    percent = min(95, (completed / len(segments)) * 95)
                    progress_callback({
                        "status": "downloading",
                        "percent": round(percent, 1),
                        "filename": os.path.basename(output_path),
                    })

                if completed % 50 == 0:
                    log.info(f"Downloaded {completed}/{len(segments)} segments")

        log.info(f"All {len(segments)} segments downloaded, muxing with ffmpeg...")

        with open(concat_file, "w") as f:
            for sf in segment_files:
                f.write(f"file '{sf}'\n")

        if progress_callback:
            progress_callback({
                "status": "downloading",
                "percent": 96,
                "filename": os.path.basename(output_path),
            })

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path,
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed (code {process.returncode}): {stderr[-500:]}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("ffmpeg produced empty file after concat")

        file_size = os.path.getsize(output_path)
        log.info(f"Download complete via httpx: {output_path} ({file_size} bytes)")
        if progress_callback:
            progress_callback({
                "status": "done",
                "percent": 100,
                "filename": os.path.basename(output_path),
            })
        return output_path

    finally:
        client.close()
        for sf in segment_files:
            if sf:
                try:
                    os.remove(sf)
                except OSError:
                    pass
        if concat_file:
            try:
                os.remove(concat_file)
            except OSError:
                pass
        if tmpdir:
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass


def parse_best_variant(master_content, master_url):
    if "#EXT-X-STREAM-INF" not in master_content:
        return master_url

    base_url = master_url.rsplit("/", 1)[0] + "/"
    lines = master_content.strip().splitlines()
    variants = []

    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            bw_match = re.search(r"BANDWIDTH=(\d+)", line)
            res_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            bw = int(bw_match.group(1)) if bw_match else 0
            height = int(res_match.group(2)) if res_match else 0
            if i + 1 < len(lines):
                variant_path = lines[i + 1].strip()
                if variant_path.startswith("http"):
                    variant_url = variant_path
                else:
                    variant_url = base_url + variant_path
                variants.append((bw, height, variant_url))

    if not variants:
        return master_url

    variants.sort(key=lambda v: v[1], reverse=True)
    return variants[0][2]


def parse_segments(variant_content, variant_url):
    base_url = variant_url.rsplit("/", 1)[0] + "/"
    segments = []
    for line in variant_content.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("http"):
            segments.append(line)
        else:
            segments.append(base_url + line)
    return segments
