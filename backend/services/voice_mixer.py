import asyncio
import logging
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
        Renders Full HD 1080p video in a single optimized pass:
        1. Subtle 1.06x anti-Content-ID crop + crisp 1920x1080 Full HD scale.
        2. Viral yellow uppercase creator captions burned directly onto video.
        3. Preserves original game audio cleanly.
        4. Bounded CPU threads (-threads 2) and web-friendly bitrate (~3.5 Mbps)
           so Railway stays responsive and video buffers smoothly in browsers.
        """
        out_video_path = EXPORTS_DIR / output_filename

        safe_ass_path = str(Path(ass_subtitles_path).resolve()).replace("\\", "/").replace(":", "\\:")
        vf_chain = (
            "crop=iw*0.943:ih*0.943:(iw-iw*0.943)/2:(ih-ih*0.943)/2,"
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,"
            f"ass='{safe_ass_path}'"
        )

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-threads", "2",
            "-i", str(stitched_video_path),
            "-vf", vf_chain,
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
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                err_msg = res.stderr.decode("utf-8", errors="ignore")[-400:]
                logger.warning(f"ASS burn-in failed ({err_msg}), retrying 1080p encode without ASS filter.")
                vf_fallback = (
                    "crop=iw*0.943:ih*0.943:(iw-iw*0.943)/2:(ih-ih*0.943)/2,"
                    "scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
                )
                cmd_fallback = [
                    self.ffmpeg_path,
                    "-y",
                    "-threads", "2",
                    "-i", str(stitched_video_path),
                    "-vf", vf_fallback,
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "25",
                    "-maxrate", "3500k",
                    "-bufsize", "7000k",
                    "-pix_fmt", "yuv420p",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(out_video_path)
                ]
                subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
            if res.returncode != 0:
                logger.error(f"Voiceover mix failed: {res.stderr.decode('utf-8', errors='ignore')[-300:]}")
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
