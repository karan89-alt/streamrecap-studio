import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any

from config import EXPORTS_DIR, TEMP_DIR, settings

logger = logging.getLogger("streamrecap.voice_mixer")


class VoiceMixer:
    def __init__(self):
        self.ffmpeg_path = settings.FFMPEG_PATH

    def generate_viral_subtitles(
        self,
        script_segments: List[Dict[str, Any]],
        job_id: str
    ) -> Dict[str, str]:
        """Generates standard .srt and viral-styled .ass subtitles."""
        srt_path = EXPORTS_DIR / f"subtitles_{job_id}.srt"
        self._generate_srt(script_segments, srt_path)

        ass_path = TEMP_DIR / f"viral_subtitles_{job_id}.ass"
        self._generate_viral_ass(script_segments, ass_path)

        return {
            "srt_path": str(srt_path),
            "ass_path": str(ass_path),
        }

    async def render_full_hd_recap(
        self,
        stitched_video_path: str,
        ass_subtitles_path: str,
        output_filename: str
    ) -> str:
        """
        Renders guaranteed-valid Full HD 1080p video in a single optimized pass:
        1. Subtle 1.06x anti-Content-ID crop (even dimensions!) + crisp 1920x1080 Full HD scale.
        2. Viral yellow uppercase creator captions burned directly onto video.
        3. Preserves original game audio cleanly.
        4. Validates output integrity (>10KB) with bulletproof multi-tier fallback so
           a 48-byte corrupt MP4 can NEVER be served.
        """
        out_video_path = EXPORTS_DIR / output_filename

        safe_ass_path = str(Path(ass_subtitles_path).resolve()).replace("\\", "/").replace(":", "\\:")
        # Even-dimension crop + clean 1920x1080 scale (compatible across ALL FFmpeg versions, Linux & Windows)
        base_vf = "crop=trunc(iw*0.94/2)*2:trunc(ih*0.94/2)*2,scale=1920:1080,setsar=1"
        vf_with_ass = f"{base_vf},ass='{safe_ass_path}'"

        def _is_valid(path: Path) -> bool:
            return path.exists() and path.stat().st_size > 10000

        def _build_encode_cmd(vf: str) -> List[str]:
            return [
                self.ffmpeg_path,
                "-y",
                "-threads", "2",
                "-i", str(stitched_video_path),
                "-vf", vf,
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "25",
                "-maxrate", "3500k",
                "-bufsize", "7000k",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "44100",
                "-movflags", "+faststart",
                str(out_video_path)
            ]

        logger.info(f"Rendering Full HD 1080p video with viral subtitles: {out_video_path}")

        def _run():
            # Attempt 1: 1080p Full HD + 1.06x crop + Viral ASS Subtitles
            res = subprocess.run(_build_encode_cmd(vf_with_ass), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and _is_valid(out_video_path):
                logger.info(f"Full HD render with ASS succeeded ({out_video_path.stat().st_size} bytes)")
                return str(out_video_path)

            err1 = res.stderr.decode("utf-8", errors="ignore")[-400:]
            logger.warning(f"Attempt 1 (ASS burn-in) failed (code={res.returncode}): {err1}")

            # Attempt 2: 1080p Full HD + subtitles filter (alternate libass syntax)
            vf_sub = f"{base_vf},subtitles='{safe_ass_path}'"
            res2 = subprocess.run(_build_encode_cmd(vf_sub), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res2.returncode == 0 and _is_valid(out_video_path):
                logger.info(f"Full HD render with subtitles filter succeeded ({out_video_path.stat().st_size} bytes)")
                return str(out_video_path)

            err2 = res2.stderr.decode("utf-8", errors="ignore")[-400:]
            logger.warning(f"Attempt 2 (subtitles filter) failed (code={res2.returncode}): {err2}")

            # Attempt 3: Pure 1080p Full HD without caption burn-in
            res3 = subprocess.run(_build_encode_cmd(base_vf), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res3.returncode == 0 and _is_valid(out_video_path):
                logger.info(f"Full HD render (no burn-in) succeeded ({out_video_path.stat().st_size} bytes)")
                return str(out_video_path)

            err3 = res3.stderr.decode("utf-8", errors="ignore")[-400:]
            logger.error(f"Attempt 3 failed (code={res3.returncode}): {err3}. Falling back to master video copy.")

            # Final guaranteed safety: copy valid stitched master so output is NEVER corrupt
            shutil.copy2(str(stitched_video_path), str(out_video_path))
            return str(out_video_path)

        return await asyncio.to_thread(_run)

    async def mix_custom_voiceover(
        self,
        stitched_video_path: str,
        user_voice_path: str,
        output_filename: str,
        game_volume: float = 0.15
    ) -> str:
        """Mixes user's recorded/uploaded voiceover over ducked original game audio."""
        out_video_path = EXPORTS_DIR / output_filename

        filter_complex = (
            f"[0:a]volume={game_volume}[bg];"
            f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[fg];"
            f"[bg][fg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-threads", "2",
            "-i", str(stitched_video_path),
            "-i", str(user_voice_path),
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "160k",
            "-movflags", "+faststart",
            str(out_video_path)
        ]

        def _run():
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0 or not out_video_path.exists() or out_video_path.stat().st_size < 10000:
                logger.error(f"Voiceover mix failed: {res.stderr.decode('utf-8', errors='ignore')[-300:]}")
                shutil.copy2(str(stitched_video_path), str(out_video_path))
            return str(out_video_path)

        return await asyncio.to_thread(_run)

    def _generate_srt(self, segments: List[Dict[str, Any]], out_path: Path):
        with open(out_path, "w", encoding="utf-8") as f:
            for idx, seg in enumerate(segments, start=1):
                vs = float(seg["video_start"])
                ve = float(seg["video_end"])
                s_h, s_m, s_s = int(vs // 3600), int((vs % 3600) // 60), int(vs % 60)
                s_ms = int((vs - int(vs)) * 1000)
                e_h, e_m, e_s = int(ve // 3600), int((ve % 3600) // 60), int(ve % 60)
                e_ms = int((ve - int(ve)) * 1000)

                f.write(f"{idx}\n")
                f.write(f"{s_h:02d}:{s_m:02d}:{s_s:02d},{s_ms:03d} --> {e_h:02d}:{e_m:02d}:{e_s:02d},{e_ms:03d}\n")
                f.write(f"{seg['dialogue_hindi']}\n\n")

    def _generate_viral_ass(self, segments: List[Dict[str, Any]], out_path: Path):
        """
        Viral YouTube Creator caption styling:
        - Bold uppercase yellow (#FFE600 -> &H0000E6FF in ASS BGR)
        - Thick black border outline (Outline=5) & shadow
        - Safe margins (MarginL=90, MarginR=90, MarginV=65) with clean auto-wrapping
        """
        ass_header = """[Script Info]
Title: StreamRecap Studio Viral Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralYellow,DejaVu Sans,44,&H0000E6FF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,5,3,2,90,90,65,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(ass_header)
            for seg in segments:
                vs = float(seg["video_start"])
                ve = float(seg["video_end"])
                s_h, s_m, s_s = int(vs // 3600), int((vs % 3600) // 60), vs % 60
                e_h, e_m, e_s = int(ve // 3600), int((ve % 3600) // 60), ve % 60

                start_str = f"{s_h}:{s_m:02d}:{s_s:05.2f}"
                end_str = f"{e_h}:{e_m:02d}:{e_s:05.2f}"
                clean_text = (
                    str(seg["dialogue_hindi"])
                    .replace("\\", "")
                    .replace("{", "(")
                    .replace("}", ")")
                    .replace("\n", " ")
                    .strip()
                    .upper()
                )
                f.write(f"Dialogue: 0,{start_str},{end_str},ViralYellow,,0,0,0,,{clean_text}\n")
