import asyncio
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Any

from config import AUDIO_DIR, EXPORTS_DIR, TEMP_DIR, settings

logger = logging.getLogger("streamrecap.voice_mixer")


class VoiceMixer:
    def __init__(self):
        self.ffmpeg_path = settings.FFMPEG_PATH

    def generate_viral_subtitles(
        self,
        script_segments: List[Dict[str, Any]],
        job_id: str
    ) -> Dict[str, str]:
        """
        Generates standard SRT subtitles and stylized ASS subtitles with viral creator fonts.
        """
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
        Renders Full HD 1080p video with:
        1. Beautiful viral font captions burned in (bold uppercase yellow with thick black outline).
        2. Original game audio preserved and balanced.
        """
        out_video_path = EXPORTS_DIR / output_filename
        loop = asyncio.get_event_loop()

        safe_ass_path = str(Path(ass_subtitles_path).resolve()).replace("\\", "/").replace(":", "\\:")
        video_filter = f"ass='{safe_ass_path}'"

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(stitched_video_path),
            "-vf", f"{video_filter},scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-map", "0:v",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(out_video_path)
        ]

        logger.info(f"Rendering Full HD video with viral font subtitles: {out_video_path}")

        def _run():
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                logger.warning(f"ASS burn-in fallback: {res.stderr.decode('utf-8', errors='ignore')}")
                cmd_fallback = [
                    self.ffmpeg_path,
                    "-y",
                    "-i", str(stitched_video_path),
                    "-c:v", "copy",
                    "-c:a", "copy",
                    str(out_video_path)
                ]
                subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return str(out_video_path)

        return await loop.run_in_executor(None, _run)

    async def mix_custom_voiceover(
        self,
        stitched_video_path: str,
        user_voice_path: str,
        output_filename: str,
        game_volume: float = 0.15
    ) -> str:
        """
        Mixes user's recorded or uploaded voiceover track over the original game audio.
        """
        out_video_path = EXPORTS_DIR / output_filename
        loop = asyncio.get_event_loop()

        filter_complex = (
            f"[0:a]volume={game_volume}[bg];"
            f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11[fg];"
            f"[bg][fg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(stitched_video_path),
            "-i", str(user_voice_path),
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            str(out_video_path)
        ]

        def _run():
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return str(out_video_path)

        return await loop.run_in_executor(None, _run)

    def _generate_srt(self, segments: List[Dict[str, Any]], out_path: Path):
        """Generates standard .srt subtitles file for video players."""
        with open(out_path, "w", encoding="utf-8") as f:
            for idx, seg in enumerate(segments, start=1):
                s_h, s_m, s_s = int(seg["video_start"] // 3600), int((seg["video_start"] % 3600) // 60), int(seg["video_start"] % 60)
                s_ms = int((seg["video_start"] - int(seg["video_start"])) * 1000)

                e_h, e_m, e_s = int(seg["video_end"] // 3600), int((seg["video_end"] % 3600) // 60), int(seg["video_end"] % 60)
                e_ms = int((seg["video_end"] - int(seg["video_end"])) * 1000)

                f.write(f"{idx}\n")
                f.write(f"{s_h:02d}:{s_m:02d}:{s_s:02d},{s_ms:03d} --> {e_h:02d}:{e_m:02d}:{e_s:02d},{e_ms:03d}\n")
                f.write(f"{seg['dialogue_hindi']}\n\n")

    def _generate_viral_ass(self, segments: List[Dict[str, Any]], out_path: Path):
        """
        Generates Advanced SubStation Alpha (.ass) with viral YouTube Creator subtitle styling:
        - Bold, uppercase typography
        - Primary color: Viral Yellow (&H0000FFFF in BGR)
        - Thick solid black outline & drop shadow
        - Bottom-center placement with safe margins
        """
        ass_header = """[Script Info]
Title: StreamRecap Studio Viral Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralYellow,Arial,46,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(ass_header)
            for seg in segments:
                s_h, s_m = int(seg["video_start"] // 3600), int((seg["video_start"] % 3600) // 60)
                s_s = seg["video_start"] % 60
                e_h, e_m = int(seg["video_end"] // 3600), int((seg["video_end"] % 3600) // 60)
                e_s = seg["video_end"] % 60

                start_str = f"{s_h}:{s_m:02d}:{s_s:05.2f}"
                end_str = f"{e_h}:{e_m:02d}:{e_s:05.2f}"
                clean_text = seg["dialogue_hindi"].replace("\n", " ").strip().upper()
                f.write(f"Dialogue: 0,{start_str},{end_str},ViralYellow,,0,0,0,,{clean_text}\n")
