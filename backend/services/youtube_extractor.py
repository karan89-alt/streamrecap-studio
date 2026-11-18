import asyncio
import base64
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import yt_dlp

from config import CLIPS_DIR, TEMP_DIR, settings

logger = logging.getLogger("streamrecap.extractor")

DEFAULT_GTA_DEMO_URL = "https://www.youtube.com/watch?v=RbVGCHFf0ZY"

# Prefer crisp 1080p30 first (2x faster download, identical 1080p sharpness for 30fps export),
# then 1080p60, then 720p — NEVER settle for blurry 360p!
HD_FORMAT_SELECTOR = (
    "bestvideo[height=1080][fps<=35][vcodec^=avc1][protocol=https]+bestaudio[ext=m4a][protocol=https]/"
    "bestvideo[height<=1080][vcodec^=avc1][protocol=https]+bestaudio[ext=m4a][protocol=https]/"
    "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
    "bestvideo[height<=1080]+bestaudio/"
    "best[height<=1080]/best"
)


def _get_cookie_args() -> List[str]:
    """Optional documented yt-dlp --cookies support via YOUTUBE_COOKIES_B64 env var (base64 or raw Netscape cookies.txt)."""
    raw_val = (os.environ.get("YOUTUBE_COOKIES_B64") or "").strip()
    if not raw_val:
        return []
    cookie_file = TEMP_DIR / "yt_cookies.txt"
    try:
        if "# Netscape" in raw_val or "\t" in raw_val:
            cookie_bytes = raw_val.encode("utf-8")
        else:
            cleaned = re.sub(r"\s+", "", raw_val)
            cookie_bytes = base64.b64decode(cleaned)
        if len(cookie_bytes) > 50:
            cookie_file.write_bytes(cookie_bytes)
            return ["--cookies", str(cookie_file)]
    except Exception as e:
        logger.warning(f"Could not parse YOUTUBE_COOKIES_B64: {e}")
    return []


class YouTubeExtractor:
    def __init__(self):
        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["hi", "en", "hi-Latn"],
            "socket_timeout": 15,
        }
        self._direct_url_cache: Dict[str, Tuple[str, Optional[str], float]] = {}
        self._url_lock = asyncio.Lock()
        self.last_debug: str = ""

    def _normalize_url(self, url: str) -> str:
        clean_url = (url or "").strip()
        if not clean_url or "sample" in clean_url.lower() or "demo" in clean_url.lower():
            return DEFAULT_GTA_DEMO_URL
        return clean_url

    async def get_stream_metadata(self, url: str) -> Dict[str, Any]:
        """Extract full YouTube metadata AND real timestamped transcript/subtitles."""
        clean_url = self._normalize_url(url)

        def _extract():
            opts = dict(self.ydl_opts)
            cookie_args = _get_cookie_args()
            if len(cookie_args) == 2:
                opts["cookiefile"] = cookie_args[1]
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(clean_url, download=False)

        try:
            info = await asyncio.wait_for(asyncio.to_thread(_extract), timeout=22.0)
            duration = int(info.get("duration") or 0)
            title = info.get("title") or "YouTube Video"
            channel = info.get("uploader") or info.get("channel") or "Creator"
            thumbnail = info.get("thumbnail") or ""
            view_count = int(info.get("view_count") or 0)
            video_id = info.get("id") or "video"
            description = (info.get("description") or "")[:1200]

            # Extract real timestamped transcript entries from subtitles / automatic_captions
            transcript_chunks = await self._fetch_transcript_from_info(info)
            logger.info(f"Metadata loaded: '{title[:50]}' ({duration}s, {len(transcript_chunks)} transcript lines)")

            return {
                "id": video_id,
                "url": clean_url,
                "title": title,
                "channel": channel,
                "duration": duration if duration > 20 else 1800,
                "thumbnail": thumbnail,
                "view_count": view_count,
                "description": description,
                "transcript": transcript_chunks,
                "is_mock": False,
            }
        except Exception as e:
            logger.warning(f"Metadata fetch failed ({e}), probing direct stream duration for: {clean_url}")
            probed_dur = 1800
            stream_pair = await self.get_direct_stream_url(clean_url)
            if stream_pair and stream_pair[0]:
                d = await self.get_clip_duration(stream_pair[0])
                if d > 20:
                    probed_dur = int(d)
            return {
                "id": "video_vod",
                "url": clean_url,
                "title": "YouTube Video",
                "channel": "Creator",
                "duration": probed_dur,
                "thumbnail": "",
                "view_count": 0,
                "description": "",
                "transcript": [],
                "is_mock": False,
            }

    async def _fetch_transcript_from_info(self, info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Downloads and parses JSON3/VTT timestamped captions so AI understands spoken video content."""
        sub_sources = info.get("subtitles") or {}
        auto_sources = info.get("automatic_captions") or {}

        sub_url = None
        sub_ext = None
        for source in (sub_sources, auto_sources):
            for lang in ("hi", "en", "en-IN", "en-US", "hi-Latn"):
                entries = source.get(lang)
                if not entries:
                    continue
                for fmt in ("json3", "vtt"):
                    for item in entries:
                        if item.get("ext") == fmt and item.get("url"):
                            sub_url = item["url"]
                            sub_ext = fmt
                            break
                    if sub_url:
                        break
                if sub_url:
                    break
            if sub_url:
                break

        if not sub_url:
            return []

        def _download_parse():
            try:
                req = urllib.request.Request(sub_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")

                chunks: List[Dict[str, Any]] = []
                if sub_ext == "json3":
                    data = json.loads(raw)
                    for ev in data.get("events", []):
                        segs = ev.get("segs")
                        if not segs:
                            continue
                        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
                        if text:
                            start_s = float(ev.get("tStartMs", 0)) / 1000.0
                            chunks.append({"start": round(start_s, 1), "text": text})
                else:
                    # Simple WebVTT parser
                    cur_start = 0.0
                    for line in raw.splitlines():
                        m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)\s+-->", line.strip())
                        if m:
                            h, mn, sc = int(m.group(1)), int(m.group(2)), int(m.group(3))
                            cur_start = h * 3600 + mn * 60 + sc
                        elif line.strip() and not line.startswith("WEBVTT") and "-->" not in line:
                            clean = re.sub(r"<[^>]+>", "", line).strip()
                            if clean:
                                chunks.append({"start": cur_start, "text": clean})
                return chunks
            except Exception as e:
                logger.warning(f"Transcript parse skipped: {e}")
                return []

        return await asyncio.to_thread(_download_parse)

    def get_transcript_window(
        self, transcript: List[Dict[str, Any]], start_sec: float, end_sec: float
    ) -> str:
        """Returns the real spoken transcript text around a specific clip interval."""
        if not transcript:
            return ""
        lines = [
            c["text"]
            for c in transcript
            if (start_sec - 5.0) <= float(c["start"]) <= (end_sec + 5.0)
        ]
        # Deduplicate adjacent repeated caption lines
        deduped = []
        for l in lines:
            if not deduped or deduped[-1] != l:
                deduped.append(l)
        return " ".join(deduped)[:300]

    async def get_direct_stream_url(
        self, url: str, force_refresh: bool = False
    ) -> Optional[Tuple[str, Optional[str]]]:
        """Extracts TRUE native 1080p DASH direct URLs (video_url, audio_url) via yt-dlp -g."""
        clean_url = self._normalize_url(url)

        async with self._url_lock:
            if not force_refresh and clean_url in self._direct_url_cache:
                v_url, a_url, ts = self._direct_url_cache[clean_url]
                if time.time() - ts < 1200:
                    return (v_url, a_url)

            cookie_args = _get_cookie_args()
            cmd_hd_visionos = [
                str(sys.executable), "-m", "yt_dlp",
                "-g",
                "--no-warnings",
                *cookie_args,
                "--extractor-args", "youtube:player_client=visionos",
                "-f", HD_FORMAT_SELECTOR,
                clean_url
            ]
            cmd_hd_default = [
                str(sys.executable), "-m", "yt_dlp",
                "-g",
                "--no-warnings",
                *cookie_args,
                "-f", HD_FORMAT_SELECTOR,
                clean_url
            ]

            cmd_hd_cookies_tv = [
                str(sys.executable), "-m", "yt_dlp",
                "-g",
                "--no-warnings",
                *cookie_args,
                "--extractor-args", "youtube:player_client=tv,web",
                "-f", HD_FORMAT_SELECTOR,
                clean_url
            ]

            def _fetch(cmd: List[str]) -> Optional[Tuple[str, Optional[str]]]:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
                if res.returncode == 0 and res.stdout.strip():
                    lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip()]
                    if len(lines) >= 2:
                        return (lines[0], lines[1])
                    elif len(lines) == 1:
                        return (lines[0], None)
                self.last_debug = f"ytdlp_g_rc={res.returncode}: {res.stderr[:220]}"
                logger.warning(self.last_debug)
                return None

            # When user cookies are configured (e.g. Railway), try cookie-compatible clients FIRST!
            candidates = (
                [("default-cookies-1080p", cmd_hd_default), ("tv-cookies-1080p", cmd_hd_cookies_tv), ("visionos-1080p", cmd_hd_visionos)]
                if cookie_args
                else [("visionos-1080p", cmd_hd_visionos), ("default-1080p", cmd_hd_default)]
            )

            for label, cmd in candidates:
                try:
                    pair = await asyncio.to_thread(_fetch, cmd)
                    if pair:
                        self._direct_url_cache[clean_url] = (pair[0], pair[1], time.time())
                        logger.info(
                            f"Cached TRUE HD stream via {label} ({'DASH 1080p+Audio' if pair[1] else 'Single'})"
                        )
                        return pair
                except Exception as e:
                    logger.warning(f"HD stream extraction ({label}) failed: {e}")

            cmd_fallback = [
                str(sys.executable), "-m", "yt_dlp",
                "-g",
                "--no-warnings",
                *cookie_args,
                "--extractor-args", "youtube:player_client=android",
                "-f", "best[height<=1080][ext=mp4]/best[ext=mp4]/best",
                clean_url
            ]
            try:
                pair = await asyncio.to_thread(_fetch, cmd_fallback)
                if pair:
                    self._direct_url_cache[clean_url] = (pair[0], pair[1], time.time())
                    return pair
            except Exception as e:
                logger.warning(f"Fallback stream extraction failed: {e}")

            return None

    async def plan_clip_intervals(
        self, metadata: Dict[str, Any], target_minutes: int, playback_speed: float = 1.0
    ) -> List[Dict[str, Any]]:
        """
        Plans non-overlapping source clip intervals across the FULL video duration.
        Each clip downloads enough source seconds to cover 1 spoken Hindi line at the chosen speed.
        """
        duration = max(45, int(metadata.get("duration") or 1800))
        target_seconds = max(60, int(target_minutes) * 60)
        speed = max(1.0, min(2.0, float(playback_speed)))

        # Average spoken Sarvam line is ~6.5s at 1x, ~4.5s at 1.5x, ~3.5s at 2x
        est_line_dur = max(3.6, 6.8 / speed)
        num_clips = max(6, min(90, int(round(target_seconds / est_line_dur)) + 2))

        # Source seconds needed per clip (with +3s safety margin for outpoint trim)
        src_clip_len = min(22.0, max(10.0, (est_line_dur * speed) + 3.5))

        safe_start = min(20.0, duration * 0.03)
        safe_end = max(safe_start + src_clip_len, duration - src_clip_len - 5.0)
        span = max(10.0, safe_end - safe_start)

        transcript = metadata.get("transcript") or []
        intervals: List[Dict[str, Any]] = []

        for i in range(num_clips):
            ratio = i / max(1, num_clips - 1)
            vod_s = safe_start + (ratio * span)
            vod_s = max(2.0, min(max(2.0, duration - src_clip_len - 2.0), vod_s))
            vod_e = min(float(duration - 1.0), vod_s + src_clip_len)

            intervals.append({
                "clip_index": i,
                "vod_start": round(vod_s, 2),
                "vod_end": round(vod_e, 2),
                "vod_start_fmt": self._fmt_mmss(vod_s),
                "vod_end_fmt": self._fmt_mmss(vod_e),
                "transcript_excerpt": self.get_transcript_window(transcript, vod_s, vod_e),
            })

        return intervals

    async def get_clip_duration(self, media_path_or_url: str) -> float:
        cmd = [
            settings.FFPROBE_PATH,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path_or_url)
        ]

        def _probe():
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
                if res.returncode == 0 and res.stdout.strip():
                    return float(res.stdout.strip())
            except Exception:
                pass
            return 0.0

        return await asyncio.to_thread(_probe)

    async def extract_clip_frame_b64(self, clip_path: str) -> Optional[str]:
        """
        Extracts a crisp 480px JPEG frame from the middle of a cut clip in ~0.05s
        so Gemini Vision can literally WATCH what is happening in that exact clip!
        """
        p = Path(clip_path)
        if not p.exists():
            return None

        dur = await self.get_clip_duration(clip_path)
        mid_t = max(0.5, min(dur * 0.45, dur - 0.5)) if dur > 1.5 else 0.5
        frame_path = TEMP_DIR / f"frame_{p.stem}.jpg"

        def _grab():
            cmd = [
                settings.FFMPEG_PATH,
                "-y",
                "-ss", f"{mid_t:.2f}",
                "-i", str(p),
                "-vframes", "1",
                "-vf", "scale=480:-1",
                "-q:v", "6",
                str(frame_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if res.returncode == 0 and frame_path.exists() and frame_path.stat().st_size > 1000:
                b64 = base64.b64encode(frame_path.read_bytes()).decode("utf-8")
                frame_path.unlink(missing_ok=True)
                return b64
            return None

        return await asyncio.to_thread(_grab)

    async def download_section(
        self,
        url: str,
        start_sec: float,
        end_sec: float,
        output_filename: str,
        max_duration: float = 3000.0,
    ) -> Optional[str]:
        """Extracts TRUE native 1080p video + stereo AAC audio clip directly from YouTube DASH streams."""
        out_path = CLIPS_DIR / output_filename
        if out_path.exists() and out_path.stat().st_size > 10000:
            dur = await self.get_clip_duration(str(out_path))
            if dur >= 1.5:
                return str(out_path)

        clean_url = self._normalize_url(url)
        clip_dur = max(4.0, min(30.0, float(end_sec - start_sec)))
        safe_start = max(0.0, min(float(start_sec), max(0.0, float(max_duration) - clip_dur - 2.0)))

        stream_pair = await self.get_direct_stream_url(clean_url)
        if stream_pair:
            v_url, a_url = stream_pair
            try:
                if a_url:
                    cmd_stream = [
                        settings.FFMPEG_PATH,
                        "-y",
                        "-threads", "2",
                        "-fflags", "+genpts",
                        "-reconnect", "1",
                        "-reconnect_streamed", "1",
                        "-reconnect_delay_max", "5",
                        "-ss", f"{safe_start:.2f}",
                        "-i", v_url,
                        "-reconnect", "1",
                        "-reconnect_streamed", "1",
                        "-reconnect_delay_max", "5",
                        "-ss", f"{safe_start:.2f}",
                        "-i", a_url,
                        "-t", f"{clip_dur:.2f}",
                        "-map", "0:v:0",
                        "-map", "1:a:0",
                        "-c:v", "copy",
                        "-c:a", "aac",
                        "-b:a", "128k",
                        "-avoid_negative_ts", "make_zero",
                        str(out_path)
                    ]
                else:
                    cmd_stream = [
                        settings.FFMPEG_PATH,
                        "-y",
                        "-threads", "2",
                        "-reconnect", "1",
                        "-reconnect_streamed", "1",
                        "-reconnect_delay_max", "5",
                        "-ss", f"{safe_start:.2f}",
                        "-i", v_url,
                        "-t", f"{clip_dur:.2f}",
                        "-c", "copy",
                        "-avoid_negative_ts", "make_zero",
                        str(out_path)
                    ]

                def _run_ffmpeg():
                    res = subprocess.run(cmd_stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
                    if res.returncode != 0:
                        self.last_debug = f"ff_rc={res.returncode}: {res.stderr.decode('utf-8', errors='ignore')[-220:]}"
                    return res.returncode

                code = await asyncio.to_thread(_run_ffmpeg)
                if code == 0 and out_path.exists() and out_path.stat().st_size > 10000:
                    real_dur = await self.get_clip_duration(str(out_path))
                    if real_dur >= 1.5:
                        logger.info(f"True HD clip {output_filename} extracted ({real_dur:.2f}s)")
                        return str(out_path)
            except Exception as e:
                logger.warning(f"Direct HD stream cut failed for {output_filename}: {e}")

        # Method 2: yt-dlp --download-sections fallback
        try:
            start_fmt = self._format_timestamp(safe_start)
            end_fmt = self._format_timestamp(safe_start + clip_dur)
            section_arg = f"*{start_fmt}-{end_fmt}"
            cookie_args = _get_cookie_args()

            cmd_ytdlp = [
                str(sys.executable), "-m", "yt_dlp",
                "--no-warnings",
                *cookie_args,
                "--download-sections", section_arg,
                "-f", HD_FORMAT_SELECTOR,
                "--merge-output-format", "mp4",
                "--ffmpeg-location", settings.FFMPEG_PATH,
                "-o", str(out_path),
                clean_url
            ]

            def _run_ytdlp():
                res = subprocess.run(cmd_ytdlp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
                return res.returncode

            code = await asyncio.to_thread(_run_ytdlp)
            if code == 0 and out_path.exists() and out_path.stat().st_size > 10000:
                real_dur = await self.get_clip_duration(str(out_path))
                if real_dur >= 1.5:
                    return str(out_path)
        except Exception as e:
            logger.error(f"yt-dlp HD fallback failed for {output_filename}: {e}")

        if out_path.exists():
            try:
                out_path.unlink()
            except Exception:
                pass
        return None

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _fmt_mmss(secs: float) -> str:
        s = max(0, int(secs))
        return f"{s // 60:02d}:{s % 60:02d}"
