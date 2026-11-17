import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any

from config import CLIPS_DIR, EXPORTS_DIR, TEMP_DIR, settings

logger = logging.getLogger("streamrecap.stitcher")


class VideoStitcher:
    """
    Video Stitcher with YouTube Monetization & Anti-Copyright Transformative Safeguards:
    1. Subtle 1.06x scale & crop (`crop=iw*0.94:ih*0.94,scale=1920:1080`) to evade automated frame hashes.
    2. In-game radio music suppression (bandpass/lowpass filters + 15% game audio suppression).
    3. Seamless concat into a master 1080p recap video ready for audio dubbing or playback.
    """

    def __init__(self):
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.ffprobe_path = settings.FFPROBE_PATH

    async def process_and_stitch_clips(
        self,
        clip_paths: List[str],
        output_filename: str,
        job_id: str = "default",
        progress_callback=None
    ) -> str:
        """
        Takes raw downloaded clips, applies anti-Content-ID transformations,
        and stitches them into a cohesive 1080p video.
        """
        final_video_path = EXPORTS_DIR / output_filename
        if final_video_path.exists() and final_video_path.stat().st_size > 1000:
            return str(final_video_path)

        loop = asyncio.get_event_loop()

        # Step 1: Preprocess each clip with anti-Content-ID transform
        processed_clips = []
        total = len(clip_paths)

        for i, clip_file in enumerate(clip_paths):
            clip_path = Path(clip_file)
            if not clip_path.exists():
                logger.warning(f"Clip not found: {clip_path}")
                continue

            processed_name = f"proc_{job_id}_{i:03d}_{clip_path.name}"
            processed_path = TEMP_DIR / processed_name

            # If already processed or already a pre-formatted clip, use directly
            if clip_path.name.startswith("clip_") and clip_path.stat().st_size > 1000:
                processed_clips.append(clip_path)
            else:
                if not processed_path.exists() or processed_path.stat().st_size < 1000:
                    await self._apply_transformative_filters(clip_path, processed_path)
                if processed_path.exists():
                    processed_clips.append(processed_path)

            if progress_callback:
                pct = int(((i + 1) / total) * 100)
                await progress_callback(pct, f"Applied anti-copyright transforms to clip {i + 1}/{total}")

        if not processed_clips:
            raise RuntimeError("No clips available to stitch!")

        # Step 2: Build concat list file
        concat_txt = TEMP_DIR / f"concat_{job_id}.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for p in processed_clips:
                # Concat demuxer expects forward slashes or escaped backslashes
                safe_path = str(p.resolve()).replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        # Step 3: Run FFmpeg concat demuxer (stream copy is instant because all clips are pre-normalized)
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy",
            "-movflags", "+faststart",
            str(final_video_path)
        ]

        logger.info(f"Stitching {len(processed_clips)} clips into {final_video_path}...")
        
        def _run_concat():
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                logger.error(f"FFmpeg concat failed: {res.stderr.decode('utf-8', errors='ignore')}")
                # Fallback to direct re-encode concat filter if demuxer fails
                self._fallback_filter_concat(processed_clips, final_video_path)

        await loop.run_in_executor(None, _run_concat)

        return str(final_video_path)

    async def _apply_transformative_filters(self, input_path: Path, output_path: Path):
        """
        Applies:
        - 1.06x subtle zoom/crop (`crop=iw*0.94:ih*0.94`)
        - Scale to standard 1920x1080 30fps
        - In-game radio music suppression (highpass=f=120, lowpass=f=6000, volume ducking to 0.18)
          This prevents in-game copyrighted car radio stations from triggering YouTube Content ID claims!
        """
        # Video filter: crop slightly from center (1.06x zoom) then scale to 1920x1080
        vf = (
            "crop=iw*0.943:ih*0.943:(iw-iw*0.943)/2:(ih-ih*0.943)/2,"
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,"
            "fps=30"
        )
        # Audio filter: duck volume and filter frequencies typical of copyrighted radio tracks
        af = "volume=0.18,highpass=f=120,lowpass=f=6500"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(input_path),
            "-vf", vf,
            "-af", af,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            str(output_path)
        ]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        )

    def _fallback_filter_concat(self, clips: List[Path], out_file: Path):
        """Fallback filter complex concat if demuxer timestamps mismatch."""
        inputs = []
        filter_str = ""
        for i, clip in enumerate(clips):
            inputs.extend(["-i", str(clip)])
            filter_str += f"[{i}:v][{i}:a]"
        filter_str += f"concat=n={len(clips)}:v=1:a=1[v][a]"

        cmd = [
            self.ffmpeg_path,
            "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(out_file)
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
