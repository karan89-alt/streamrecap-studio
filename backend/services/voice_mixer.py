import asyncio
import base64
import json
import logging
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Any, Optional

from config import AUDIO_DIR, EXPORTS_DIR, TEMP_DIR, settings

logger = logging.getLogger("streamrecap.voice_mixer")

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"

# Curated Indian Voices on Sarvam AI bulbul:v3
SARVAM_VOICES: List[Dict[str, str]] = [
    {"id": "shubh", "name": "Shubh", "gender": "male", "style": "Energetic Narrator"},
    {"id": "kabir", "name": "Kabir", "gender": "male", "style": "Deep Cinematic"},
    {"id": "aditya", "name": "Aditya", "gender": "male", "style": "Storyteller"},
    {"id": "rahul", "name": "Rahul", "gender": "male", "style": "Funny / Roast"},
    {"id": "rohan", "name": "Rohan", "gender": "male", "style": "Fast Action"},
    {"id": "amit", "name": "Amit", "gender": "male", "style": "Documentary"},
    {"id": "dev", "name": "Dev", "gender": "male", "style": "Suspense"},
    {"id": "mohit", "name": "Mohit", "gender": "male", "style": "Gaming"},
    {"id": "ritu", "name": "Ritu", "gender": "female", "style": "Expressive Narrator"},
    {"id": "priya", "name": "Priya", "gender": "female", "style": "Storyteller"},
    {"id": "neha", "name": "Neha", "gender": "female", "style": "Energetic"},
    {"id": "kavya", "name": "Kavya", "gender": "female", "style": "Dramatic"},
    {"id": "shreya", "name": "Shreya", "gender": "female", "style": "Clear Explainer"},
    {"id": "shruti", "name": "Shruti", "gender": "female", "style": "Documentary"},
]

VALID_SPEAKERS = {v["id"] for v in SARVAM_VOICES}


class VoiceMixer:
    def __init__(self):
        self.ffmpeg_path = settings.FFMPEG_PATH
        self.ffprobe_path = settings.FFPROBE_PATH
        self.last_render_info: Dict[str, Any] = {}

    def _probe_duration(self, path: Path) -> float:
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip())
        except Exception:
            pass
        return 0.0

    def _call_sarvam_tts_sync(self, text: str, speaker: str, api_key: str, pace: float = 1.06) -> bytes:
        """Calls Sarvam AI bulbul:v3 TTS API and returns raw WAV bytes."""
        safe_speaker = speaker.lower().strip()
        if safe_speaker not in VALID_SPEAKERS:
            safe_speaker = "shubh"

        payload = {
            "inputs": [text[:490]],
            "target_language_code": "hi-IN",
            "speaker": safe_speaker,
            "model": "bulbul:v3",
            "pace": pace,
        }
        headers = {
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        }

        last_err = None
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    SARVAM_TTS_URL,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=25) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    audios = data.get("audios") or []
                    if audios:
                        return base64.b64decode(audios[0])
            except Exception as e:
                last_err = e
                logger.warning(f"Sarvam TTS attempt {attempt + 1} failed: {e}")

        raise RuntimeError(f"Sarvam AI TTS failed: {last_err}")

    async def synthesize_sarvam_audio_timeline(
        self,
        script_segments: List[Dict[str, Any]],
        speaker: str,
        job_id: str,
        target_seconds: int,
        playback_speed: float = 1.0,
        api_key: Optional[str] = None,
        progress_callback=None,
    ) -> Optional[Dict[str, Any]]:
        """
        Audio-First Synthesis via Sarvam AI (bulbul:v3) at the EXACT selected speed (1x - 2x):
        1. Synthesizes every Hindi line at exact pace=playback_speed (1.0, 1.25, 1.5, 1.75, or 2.0).
        2. Measures exact duration of every generated WAV clip + proportional pause.
        3. Sets exact source_duration = audio_dur * playback_speed so video clips speed up by
           exact playback_speed to match every spoken syllable with ZERO drift!
        """
        key = (api_key or settings.SARVAM_API_KEY or "").strip()
        if not key:
            logger.warning("No SARVAM_API_KEY provided — skipping Sarvam AI TTS.")
            return None

        speed = max(1.0, min(2.0, float(playback_speed)))
        sem = asyncio.Semaphore(5)
        total = len(script_segments)
        completed = 0
        pause_sec = round(max(0.12, 0.25 / speed), 3)

        async def _synth_one(idx: int, seg: Dict[str, Any]):
            nonlocal completed
            raw_wav = AUDIO_DIR / f"sarvam_raw_{job_id}_{idx:03d}.wav"
            padded_wav = AUDIO_DIR / f"sarvam_pad_{job_id}_{idx:03d}.wav"

            async with sem:
                text = str(seg.get("dialogue_hindi", "")).strip()
                if not text:
                    text = "Dekhiye aage kya hota hai!"

                wav_bytes = await asyncio.to_thread(
                    self._call_sarvam_tts_sync, text, speaker, key, speed
                )
                raw_wav.write_bytes(wav_bytes)

                def _pad_and_measure():
                    cmd = [
                        self.ffmpeg_path,
                        "-y",
                        "-i", str(raw_wav),
                        "-af", f"apad=pad_dur={pause_sec}",
                        "-ar", "44100",
                        "-ac", "2",
                        "-c:a", "pcm_s16le",
                        str(padded_wav)
                    ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                    dur = self._probe_duration(padded_wav)
                    raw_wav.unlink(missing_ok=True)
                    return dur

                exact_dur = await asyncio.to_thread(_pad_and_measure)
                completed += 1
                if progress_callback:
                    await progress_callback(completed, total)

                return idx, padded_wav, max(1.5, exact_dur)

        tasks = [_synth_one(i, seg) for i, seg in enumerate(script_segments)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_items = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"Sarvam segment error: {r}")
                continue
            valid_items.append(r)

        if not valid_items:
            return None

        valid_items.sort(key=lambda x: x[0])

        synced_segments: List[Dict[str, Any]] = []
        selected_wavs: List[Path] = []
        cumulative_time = 0.0

        for idx, wav_path, audio_dur in valid_items:
            if cumulative_time > 0 and (cumulative_time + audio_dur) > (target_seconds + 15):
                break

            seg = dict(script_segments[idx])
            seg["clip_index"] = len(synced_segments)
            seg["id"] = f"seg_{len(synced_segments) + 1:03d}"
            seg["video_start"] = round(cumulative_time, 3)
            seg["video_end"] = round(cumulative_time + audio_dur, 3)
            seg["duration"] = round(audio_dur, 3)
            seg["source_duration"] = round(audio_dur * speed, 3)
            seg["video_start_fmt"] = self._fmt_mmss(cumulative_time)
            seg["video_end_fmt"] = self._fmt_mmss(cumulative_time + audio_dur)
            seg["vod_end"] = round(float(seg["vod_start"]) + (audio_dur * speed) + 3.0, 2)

            cumulative_time += audio_dur
            synced_segments.append(seg)
            selected_wavs.append(wav_path)

        # Concatenate all Sarvam WAV clips into one broadcast-normalized master voiceover track
        voice_concat_txt = TEMP_DIR / f"voice_concat_{job_id}.txt"
        with open(voice_concat_txt, "w", encoding="utf-8") as f:
            for wp in selected_wavs:
                safe_p = str(wp.resolve()).replace("\\", "/")
                f.write(f"file '{safe_p}'\n")

        master_voice_path = AUDIO_DIR / f"master_sarvam_{job_id}.m4a"

        def _merge_voice():
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-threads", "2",
                "-f", "concat",
                "-safe", "0",
                "-i", str(voice_concat_txt),
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                str(master_voice_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if res.returncode != 0:
                logger.warning(f"Loudnorm merge fallback: {res.stderr.decode('utf-8', errors='ignore')[-200:]}")
                cmd_simple = [
                    self.ffmpeg_path, "-y", "-f", "concat", "-safe", "0",
                    "-i", str(voice_concat_txt), "-c:a", "aac", "-b:a", "192k",
                    str(master_voice_path)
                ]
                subprocess.run(cmd_simple, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

            # Cleanup individual WAV chunks
            for _, wp, _ in valid_items:
                wp.unlink(missing_ok=True)
            voice_concat_txt.unlink(missing_ok=True)

        await asyncio.to_thread(_merge_voice)

        if not master_voice_path.exists() or master_voice_path.stat().st_size < 5000:
            return None

        return {
            "master_voice_path": str(master_voice_path),
            "segments": synced_segments,
            "total_duration": round(cumulative_time, 3),
            "speaker": speaker,
        }

    def generate_viral_subtitles(
        self,
        script_segments: List[Dict[str, Any]],
        job_id: str
    ) -> Dict[str, str]:
        """Generates standard .srt and viral-styled .ass subtitles synced to Sarvam audio."""
        srt_path = EXPORTS_DIR / f"subtitles_{job_id}.srt"
        self._generate_srt(script_segments, srt_path)

        ass_path = TEMP_DIR / f"viral_subtitles_{job_id}.ass"
        self._generate_viral_ass(script_segments, ass_path)

        return {
            "srt_path": str(srt_path),
            "ass_path": str(ass_path),
        }

    async def render_audio_driven_1080p_recap(
        self,
        concat_txt_path: str,
        ass_subtitles_path: str,
        output_filename: str,
        master_voice_path: Optional[str] = None,
        game_audio_filename: Optional[str] = None,
        playback_speed: float = 1.0,
    ) -> Dict[str, str]:
        """
        Single-Pass Speed-Exact Audio-Driven Full HD 1080p Render:
        - Reads frame-accurate concat_txt_path (each clip has exact `outpoint = audio_dur * speed`).
        - Applies `setpts=PTS/{speed}` FIRST so video clips run at EXACT selected speed (1x..2x)
          and match the Sarvam AI voiceover duration to the millisecond!
        - Applies 1.06x crop + Lanczos 1920x1080 scale + single viral yellow ASS captions AFTER setpts.
        - Extracts exact speed-matched original game audio (`atempo={speed}`) for the toggle button!
        """
        out_video_path = EXPORTS_DIR / output_filename
        out_game_audio_path = EXPORTS_DIR / game_audio_filename if game_audio_filename else None
        speed = max(1.0, min(2.0, float(playback_speed)))

        safe_ass_path = str(Path(ass_subtitles_path).resolve()).replace("\\", "/").replace(":", "\\:")
        speed_vf = f"setpts=PTS/{speed}," if speed > 1.0 else ""
        base_vf = f"{speed_vf}crop=trunc(iw*0.94/2)*2:trunc(ih*0.94/2)*2,scale=1920:1080:flags=lanczos,fps=30,setsar=1"
        vf_with_ass = f"{base_vf},ass='{safe_ass_path}'"

        def _is_valid(path: Path) -> bool:
            return path.exists() and path.stat().st_size > 10000

        def _build_cmd(vf: str) -> List[str]:
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-threads", "2",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_txt_path),
            ]
            if master_voice_path and Path(master_voice_path).exists():
                cmd.extend(["-i", str(master_voice_path)])
                cmd.extend([
                    "-vf", vf,
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-shortest",
                ])
            else:
                audio_speed_af = f"atempo={speed}," if speed > 1.0 else ""
                cmd.extend([
                    "-vf", vf,
                    "-af", f"aresample=async=1:first_pts=0,{audio_speed_af}highpass=f=100,lowpass=f=7500",
                    "-map", "0:v:0",
                    "-map", "0:a:0?",
                ])

            cmd.extend([
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-crf", "19",
                "-maxrate", "6500k",
                "-bufsize", "12000k",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-movflags", "+faststart",
                str(out_video_path)
            ])
            return cmd

        def _run():
            # 1. Extract exact speed-matched original game audio track (.m4a)
            if out_game_audio_path:
                af_chain = (
                    f"aresample=async=1:first_pts=0,atempo={speed},highpass=f=100,lowpass=f=7500"
                    if speed > 1.0
                    else "aresample=async=1:first_pts=0,highpass=f=100,lowpass=f=7500"
                )
                cmd_game_audio = [
                    self.ffmpeg_path,
                    "-y",
                    "-threads", "2",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_txt_path),
                    "-vn",
                    "-af", af_chain,
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-ar", "44100",
                    "-movflags", "+faststart",
                    str(out_game_audio_path)
                ]
                subprocess.run(cmd_game_audio, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

            # 2. Attempt 1: Full HD 1080p + Speed + 1.06x Crop + Single Viral ASS Captions + Sarvam Voice
            res = subprocess.run(_build_cmd(vf_with_ass), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and _is_valid(out_video_path):
                sz = out_video_path.stat().st_size
                self.last_render_info = {
                    "mode": "1080p_sarvam_audio_driven_ass",
                    "speed": speed,
                    "bytes": sz,
                    "returncode": 0
                }
                logger.info(f"Audio-driven 1080p ({speed}x) + Sarvam AI render succeeded ({sz} bytes)")
                return

            err1 = res.stderr.decode("utf-8", errors="ignore")[-400:]
            logger.warning(f"Attempt 1 failed (code={res.returncode}): {err1}")

            # Attempt 2: 720p HD + Speed + Viral ASS + Sarvam Voice
            vf_720 = f"{speed_vf}crop=trunc(iw*0.94/2)*2:trunc(ih*0.94/2)*2,scale=1280:720:flags=lanczos,fps=30,setsar=1,ass='{safe_ass_path}'"
            res2 = subprocess.run(_build_cmd(vf_720), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res2.returncode == 0 and _is_valid(out_video_path):
                sz = out_video_path.stat().st_size
                self.last_render_info = {"mode": "720p_sarvam_ass", "speed": speed, "bytes": sz, "err1": err1}
                return

            err2 = res2.stderr.decode("utf-8", errors="ignore")[-400:]
            logger.warning(f"Attempt 2 failed (code={res2.returncode}): {err2}")

            # Attempt 3: Pure 1080p + Speed without ASS burn-in
            res3 = subprocess.run(_build_cmd(base_vf), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res3.returncode == 0 and _is_valid(out_video_path):
                self.last_render_info = {"mode": "1080p_no_ass", "speed": speed, "bytes": out_video_path.stat().st_size, "err1": err1}
                return

            raise RuntimeError(f"FFmpeg render failed: {err1}")

        await asyncio.to_thread(_run)
        return {
            "final_video_path": str(out_video_path),
            "game_audio_path": str(out_game_audio_path) if (out_game_audio_path and out_game_audio_path.exists()) else "",
        }

    async def mix_custom_voiceover(
        self,
        stitched_video_path: str,
        user_voice_path: str,
        output_filename: str,
        game_volume: float = 0.15
    ) -> str:
        """Mixes user's recorded/uploaded voiceover over ducked audio."""
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
            "-b:a", "192k",
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
        Single crisp Viral YouTube Creator caption layer:
        - Bold uppercase yellow (#FFE600 -> &H0000E6FF in ASS BGR)
        - Thick black border outline (Outline=5) & shadow
        - Generous margins for crisp 2-line wrapping
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
Style: ViralYellow,DejaVu Sans,44,&H0000E6FF,&H000000FF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,5,3,2,100,100,62,1

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

    @staticmethod
    def _fmt_mmss(secs: float) -> str:
        s = max(0, int(secs))
        return f"{s // 60:02d}:{s % 60:02d}"
