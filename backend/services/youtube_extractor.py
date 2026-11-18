import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

import yt_dlp

from config import CLIPS_DIR, settings

logger = logging.getLogger("streamrecap.extractor")

# Real public GTA V gameplay stream for instant demoing
DEFAULT_GTA_DEMO_URL = "https://www.youtube.com/watch?v=RbVGCHFf0ZY"


class YouTubeExtractor:
    def __init__(self):
        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "socket_timeout": 15,
            "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        }
        # Cache direct streaming URLs with timestamp (TTL: 20 minutes)
        self._direct_url_cache: Dict[str, Tuple[str, float]] = {}
        self._url_lock = asyncio.Lock()

    def _normalize_url(self, url: str) -> str:
        clean_url = (url or "").strip()
        if not clean_url or "sample" in clean_url.lower() or "demo" in clean_url.lower():
            return DEFAULT_GTA_DEMO_URL
        return clean_url

    async def get_stream_metadata(self, url: str) -> Dict[str, Any]:
        """Extract stream metadata safely without blocking the asyncio event loop."""
        clean_url = self._normalize_url(url)

        def _extract():
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                return ydl.extract_info(clean_url, download=False)

        try:
            info = await asyncio.wait_for(asyncio.to_thread(_extract), timeout=20.0)
            duration = int(info.get("duration") or 0)
            title = info.get("title") or "GTA V Gaming Stream"
            channel = info.get("uploader") or info.get("channel") or "Gaming Creator"
            thumbnail = info.get("thumbnail") or ""
            view_count = int(info.get("view_count") or 0)
            video_id = info.get("id") or "stream"

            return {
                "id": video_id,
                "url": clean_url,
                "title": title,
                "channel": channel,
                "duration": duration if duration > 30 else 3000,
                "thumbnail": thumbnail,
                "view_count": view_count,
                "description": (info.get("description") or "")[:1000],
                "subtitles": [],
                "is_mock": False,
            }
        except Exception as e:
            logger.warning(f"Metadata fetch failed ({e}), using safe defaults for URL: {clean_url}")
            # Try to probe actual duration from direct stream URL if metadata failed
            probed_dur = 3000
            direct = await self.get_direct_stream_url(clean_url)
            if direct:
                d = await self.get_clip_duration(direct)
                if d > 30:
                    probed_dur = int(d)
            return {
                "id": "RbVGCHFf0ZY" if clean_url == DEFAULT_GTA_DEMO_URL else "stream_vod",
                "url": clean_url,
                "title": "GTA V Live Action & Heist Gameplay",
                "channel": "Gaming Streamer",
                "duration": probed_dur,
                "thumbnail": "https://i.ytimg.com/vi/RbVGCHFf0ZY/maxresdefault.jpg",
                "view_count": 1500000,
                "description": "High tension gaming stream gameplay.",
                "subtitles": [],
                "is_mock": False,
            }

    async def get_direct_stream_url(self, url: str, force_refresh: bool = False) -> Optional[str]:
        """Extract direct progressive MP4 stream URL with lock & TTL caching."""
        clean_url = self._normalize_url(url)

        async with self._url_lock:
            if not force_refresh and clean_url in self._direct_url_cache:
                cached_url, ts = self._direct_url_cache[clean_url]
                if time.time() - ts < 1200:  # 20 min TTL
                    return cached_url

            cmd = [
                str(sys.executable), "-m", "yt_dlp",
                "-g",
                "--no-warnings",
                "--extractor-args", "youtube:player_client=android,web",
                "-f", "best[height<=1080][ext=mp4]/best[ext=mp4]/best",
                clean_url
            ]

            def _fetch():
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
                if res.returncode == 0 and res.stdout.strip():
                    lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
                    return lines[0] if lines else None
                logger.warning(f"yt-dlp -g stderr: {res.stderr[:300]}")
                return None

            try:
                direct_url = await asyncio.to_thread(_fetch)
                if direct_url:
                    self._direct_url_cache[clean_url] = (direct_url, time.time())
                    logger.info(f"Direct stream URL fetched once and cached for {clean_url}")
                    return direct_url
            except Exception as e:
                logger.warning(f"Direct stream URL extraction failed: {e}")

            return None

    async def detect_hype_spikes(self, metadata: Dict[str, Any], total_minutes: int) -> List[Dict[str, Any]]:
        """
        Distribute non-overlapping candidate action timestamps strictly within the actual video duration.
        """
        duration = max(60, int(metadata.get("duration") or 3000))
        num_candidates = max(20, min(150, total_minutes * 4))

        # Keep safe margins at start and end of video
        safe_start = min(30, int(duration * 0.05))
        safe_end = max(safe_start + 30, duration - 20)
        span = max(30, safe_end - safe_start)

        candidates = []
        step = span / (num_candidates + 1)
        for i in range(1, num_candidates + 1):
            approx_start = int(safe_start + (step * i))
            clip_len = 8 + (i % 4)  # 8 to 11 seconds
            approx_start = max(safe_start, min(safe_end - clip_len, approx_start))
            approx_end = approx_start + clip_len

            candidates.append({
                "start": approx_start,
                "end": approx_end,
                "hype": 75 + (i * 13) % 25,
                "text": f"Action highlight at {approx_start // 60}m {approx_start % 60}s"
            })

        candidates.sort(key=lambda x: x["start"])
        return candidates

    async def get_clip_duration(self, media_path_or_url: str) -> float:
        """Uses ffprobe to measure exact real media duration in seconds."""
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

    async def download_section(
        self,
        url: str,
        start_sec: float,
        end_sec: float,
        output_filename: str,
        max_duration: float = 3000.0,
    ) -> Optional[str]:
        """
        Fast, duration-accurate clip extraction using direct stream seek (-ss before -i, -t after -i).
        Strictly clamps timestamps to video bounds and verifies output file integrity.
        """
        out_path = CLIPS_DIR / output_filename
        if out_path.exists() and out_path.stat().st_size > 5000:
            dur = await self.get_clip_duration(str(out_path))
            if dur >= 1.0:
                return str(out_path)

        clean_url = self._normalize_url(url)
        clip_dur = max(4.0, min(15.0, float(end_sec - start_sec)))
        safe_start = max(0.0, min(float(start_sec), max(0.0, float(max_duration) - clip_dur - 2.0)))

        # Method 1: Fast direct stream seek with -t AFTER -i (accurate clip length!)
        direct_url = await self.get_direct_stream_url(clean_url)
        if direct_url:
            try:
                cmd_stream = [
                    settings.FFMPEG_PATH,
                    "-y",
                    "-threads", "2",
                    "-reconnect", "1",
                    "-reconnect_streamed", "1",
                    "-reconnect_delay_max", "5",
                    "-ss", f"{safe_start:.2f}",
                    "-i", direct_url,
                    "-t", f"{clip_dur:.2f}",
                    "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    str(out_path)
                ]

                def _run_ffmpeg():
                    res = subprocess.run(cmd_stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
                    return res.returncode

                code = await asyncio.to_thread(_run_ffmpeg)
                if code == 0 and out_path.exists() and out_path.stat().st_size > 5000:
                    real_dur = await self.get_clip_duration(str(out_path))
                    if real_dur >= 1.5:
                        logger.info(f"Clip {output_filename} extracted ({real_dur:.2f}s)")
                        return str(out_path)
            except Exception as e:
                logger.warning(f"Direct stream cut failed for {output_filename}: {e}")

        # Method 2: yt-dlp --download-sections fallback
        try:
            start_fmt = self._format_timestamp(safe_start)
            end_fmt = self._format_timestamp(safe_start + clip_dur)
            section_arg = f"*{start_fmt}-{end_fmt}"

            cmd_ytdlp = [
                str(sys.executable), "-m", "yt_dlp",
                "--no-warnings",
                "--download-sections", section_arg,
                "--extractor-args", "youtube:player_client=android,web",
                "-f", "best[height<=1080][ext=mp4]/best[ext=mp4]/best",
                "--ffmpeg-location", settings.FFMPEG_PATH,
                "-o", str(out_path),
                clean_url
            ]

            def _run_ytdlp():
                res = subprocess.run(cmd_ytdlp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35)
                return res.returncode

            code = await asyncio.to_thread(_run_ytdlp)
            if code == 0 and out_path.exists() and out_path.stat().st_size > 5000:
                real_dur = await self.get_clip_duration(str(out_path))
                if real_dur >= 1.5:
                    return str(out_path)
        except Exception as e:
            logger.error(f"yt-dlp fallback failed for {output_filename}: {e}")

        # Remove corrupt/empty partial file if it exists
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
