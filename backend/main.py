import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from config import (
    settings,
    STORAGE_DIR,
    CLIPS_DIR,
    SCRIPTS_DIR,
    AUDIO_DIR,
    EXPORTS_DIR,
    TEMP_DIR,
)
from services.youtube_extractor import YouTubeExtractor
from services.ai_director import AIDirector
from services.voice_mixer import VoiceMixer, SARVAM_VOICES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("streamrecap.api")

app = FastAPI(
    title="StreamRecap Studio API",
    description="Audio-driven Full HD gaming recap studio powered by Sarvam AI Indian TTS & 1080p60 stream editing",
    version="3.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

JOBS: Dict[str, Dict[str, Any]] = {}
JOB_EVENT_QUEUES: Dict[str, List[asyncio.Queue]] = {}
RENDER_SEMAPHORE = asyncio.Semaphore(1)

extractor = YouTubeExtractor()
director = AIDirector()
voice_mixer = VoiceMixer()


ALLOWED_SPEEDS = [1.0, 1.25, 1.5, 1.75, 2.0]


def _normalize_speed(val: float) -> float:
    return min(ALLOWED_SPEEDS, key=lambda x: abs(x - float(val)))


# --- Models ---
class CreateRecapRequest(BaseModel):
    url: str
    target_minutes: int = 15
    story_style: str = "Explainer Storytelling"
    voice_speaker: str = "shubh"  # Sarvam AI bulbul:v3 Indian speaker
    playback_speed: float = 1.0   # 1.0, 1.25, 1.5, 1.75, or 2.0


class UpdateScriptRequest(BaseModel):
    segments: List[Dict[str, Any]]


def _fmt_mmss(secs: float) -> str:
    s = max(0, int(secs))
    return f"{s // 60:02d}:{s % 60:02d}"


def _cleanup_job_temp_files(job_id: str):
    try:
        for p in CLIPS_DIR.glob(f"clip_{job_id}_*.mp4"):
            p.unlink(missing_ok=True)
        for p in TEMP_DIR.glob(f"*{job_id}*"):
            p.unlink(missing_ok=True)
        for p in AUDIO_DIR.glob(f"sarvam_*_{job_id}_*.wav"):
            p.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Cleanup warning for {job_id}: {e}")


async def notify_job_update(job_id: str, stage_num: int, progress: int, message: str, **extra):
    if job_id not in JOBS:
        return

    job = JOBS[job_id]
    job["stage"] = stage_num
    job["progress"] = progress
    job["message"] = message
    job.update(extra)

    payload = {
        "job_id": job_id,
        "status": job.get("status", "PROCESSING"),
        "stage": stage_num,
        "progress": progress,
        "message": message,
        **extra
    }

    if job_id in JOB_EVENT_QUEUES:
        for q in list(JOB_EVENT_QUEUES[job_id]):
            await q.put(json.dumps(payload))


# --- Audio-Driven Background Pipeline ---
async def process_recap_pipeline(
    job_id: str,
    url: str,
    target_minutes: int,
    story_style: str,
    voice_speaker: str,
    playback_speed: float = 1.0,
    sarvam_key: Optional[str] = None
):
    try:
        target_minutes = max(1, min(30, int(target_minutes)))
        target_seconds = target_minutes * 60
        speed = _normalize_speed(playback_speed)
        speed_label = f"{speed:g}x"

        # Stage 1: Analyze YouTube stream
        await notify_job_update(
            job_id,
            stage_num=1,
            progress=8,
            message=f"Analyzing YouTube stream ({speed_label} mode)..."
        )

        metadata = await extractor.get_stream_metadata(url)
        stream_duration = float(metadata.get("duration") or 3000)
        hype_spikes = await extractor.detect_hype_spikes(metadata, target_minutes)

        await notify_job_update(
            job_id,
            stage_num=1,
            progress=18,
            message=f"Stream loaded: {metadata.get('title', 'Gaming Stream')[:45]}",
            metadata=metadata
        )

        # Stage 2a: Write rich Hindi script scaled to selected speed so audio fills full duration
        await notify_job_update(
            job_id,
            stage_num=2,
            progress=24,
            message=f"Writing {story_style} script for {speed_label} speed..."
        )

        script_buffer_minutes = max(target_minutes + 1, int(round(target_minutes * speed * 1.25)))
        raw_script_segments = await director.create_story_and_script(
            stream_meta=metadata,
            hype_spikes=hype_spikes,
            target_minutes=script_buffer_minutes,
            story_style=story_style
        )

        # Stage 2b: Synthesize Sarvam AI (bulbul:v3) Indian Voice at EXACT selected speed!
        await notify_job_update(
            job_id,
            stage_num=2,
            progress=30,
            message=f"Generating Sarvam AI voice ({voice_speaker.title()} @ {speed_label})..."
        )

        async def _on_tts_progress(done: int, total: int):
            pct = 30 + int((done / max(1, total)) * 20)
            await notify_job_update(
                job_id,
                stage_num=2,
                progress=pct,
                message=f"Sarvam AI ({voice_speaker.title()} @ {speed_label}): {done}/{total} lines..."
            )

        sarvam_result = await voice_mixer.synthesize_sarvam_audio_timeline(
            script_segments=raw_script_segments,
            speaker=voice_speaker,
            job_id=job_id,
            target_seconds=target_seconds,
            playback_speed=speed,
            api_key=sarvam_key,
            progress_callback=_on_tts_progress
        )

        master_voice_path: Optional[str] = None
        if sarvam_result:
            active_segments = sarvam_result["segments"]
            master_voice_path = sarvam_result["master_voice_path"]
            audio_total_fmt = _fmt_mmss(sarvam_result["total_duration"])
            await notify_job_update(
                job_id,
                stage_num=3,
                progress=52,
                message=f"Sarvam AI {speed_label} audio ready ({audio_total_fmt})! Cutting 1080p clips...",
                segments=active_segments
            )
        else:
            active_segments = raw_script_segments[: max(6, round(target_seconds / 10))]
            for seg in active_segments:
                seg["source_duration"] = round(float(seg["duration"]) * speed, 3)
            await notify_job_update(
                job_id,
                stage_num=3,
                progress=52,
                message=f"Extracting 1080p clips for {speed_label} render...",
                segments=active_segments
            )

        # Stage 3: Extract TRUE Native 1080p60 clips sized to (audio_dur * speed) + buffer!
        total_clips = len(active_segments)
        completed_downloads = 0
        dl_sem = asyncio.Semaphore(5)

        await extractor.get_direct_stream_url(metadata.get("url", url))

        async def _download_one(idx: int, seg: Dict[str, Any]):
            nonlocal completed_downloads
            clip_filename = f"clip_{job_id}_{idx:03d}.mp4"
            req_start = float(seg["vod_start"])
            needed_src = float(seg.get("source_duration") or (float(seg["duration"]) * speed))
            req_dur = needed_src + 3.0
            async with dl_sem:
                clip_path = await extractor.download_section(
                    url=metadata.get("url", url),
                    start_sec=req_start,
                    end_sec=req_start + req_dur,
                    output_filename=clip_filename,
                    max_duration=stream_duration
                )
                completed_downloads += 1
                await notify_job_update(
                    job_id,
                    stage_num=3,
                    progress=52 + int((completed_downloads / max(1, total_clips)) * 30),
                    message=f"Cutting 1080p clip {completed_downloads}/{total_clips} ({speed_label})..."
                )
                return idx, clip_path

        tasks = [_download_one(idx, seg) for idx, seg in enumerate(active_segments)]
        results = await asyncio.gather(*tasks)
        results.sort(key=lambda x: x[0])

        valid_clip_entries = []
        valid_clip_paths_only = []
        for idx, clip_path in results:
            if clip_path and Path(clip_path).exists() and Path(clip_path).stat().st_size > 10000:
                valid_clip_paths_only.append(clip_path)
            valid_clip_entries.append((idx, clip_path))

        if not valid_clip_paths_only:
            raise RuntimeError(
                f"Could not extract 1080p clips from this YouTube URL. ({extractor.last_debug[:180]})"
            )

        # Build exact concat list: outpoint = (audio_dur * speed), so after setpts=PTS/speed
        # every single video clip equals EXACT audio_dur to the millisecond!
        concat_txt = TEMP_DIR / f"concat_audio_sync_{job_id}.txt"
        final_segments: List[Dict[str, Any]] = []
        running_t = 0.0

        with open(concat_txt, "w", encoding="utf-8") as cf:
            for idx, clip_path in valid_clip_entries:
                seg = dict(active_segments[idx])
                chosen_path = clip_path if (clip_path and Path(clip_path).exists()) else valid_clip_paths_only[idx % len(valid_clip_paths_only)]
                real_clip_dur = await extractor.get_clip_duration(chosen_path)
                desired_final_dur = float(seg["duration"])
                desired_src_dur = float(seg.get("source_duration") or (desired_final_dur * speed))

                safe_p = str(Path(chosen_path).resolve()).replace("\\", "/")
                if real_clip_dur >= desired_src_dur:
                    cf.write(f"file '{safe_p}'\n")
                    cf.write(f"outpoint {desired_src_dur:.3f}\n")
                else:
                    rem = desired_src_dur
                    while rem > 0.2:
                        take = min(rem, max(1.0, real_clip_dur - 0.1))
                        cf.write(f"file '{safe_p}'\n")
                        cf.write(f"outpoint {take:.3f}\n")
                        rem -= take

                seg["video_start"] = round(running_t, 3)
                seg["video_end"] = round(running_t + desired_final_dur, 3)
                seg["video_start_fmt"] = _fmt_mmss(running_t)
                seg["video_end_fmt"] = _fmt_mmss(running_t + desired_final_dur)
                running_t += desired_final_dur
                final_segments.append(seg)

        script_file = SCRIPTS_DIR / f"script_{job_id}.json"
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(final_segments, f, indent=2, ensure_ascii=False)

        # Stage 4: Single-pass TRUE 1080p Render at EXACT speed (Video + Sarvam Voice + Game Audio + Captions)
        async with RENDER_SEMAPHORE:
            await notify_job_update(
                job_id,
                stage_num=4,
                progress=88,
                message=f"Rendering 1080p Full HD at {speed_label} with Sarvam AI voice & captions...",
                segments=final_segments
            )

            subtitle_files = voice_mixer.generate_viral_subtitles(
                script_segments=final_segments,
                job_id=job_id
            )

            final_filename = f"final_recap_{job_id}.mp4"
            game_audio_filename = f"game_audio_{job_id}.m4a"

            render_out = await voice_mixer.render_audio_driven_1080p_recap(
                concat_txt_path=str(concat_txt),
                ass_subtitles_path=subtitle_files["ass_path"],
                output_filename=final_filename,
                master_voice_path=master_voice_path,
                game_audio_filename=game_audio_filename,
                playback_speed=speed
            )

        final_url = f"/storage/exports/{final_filename}"
        game_audio_url = f"/storage/exports/{game_audio_filename}" if render_out.get("game_audio_path") else ""
        srt_url = f"/storage/exports/subtitles_{job_id}.srt"

        _cleanup_job_temp_files(job_id)

        await notify_job_update(
            job_id,
            stage_num=5,
            progress=100,
            message=f"1080p Full HD Recap Ready ({voice_speaker.title()} @ {speed_label})!",
            status="COMPLETED",
            final_video_url=final_url,
            stitched_video_url=final_url,
            game_audio_video_url=game_audio_url,
            srt_url=srt_url,
            voice_speaker=voice_speaker,
            playback_speed=speed,
            segments=final_segments,
            metadata=metadata,
            render_info=voice_mixer.last_render_info
        )

    except Exception as e:
        logger.exception(f"Pipeline error for job {job_id}: {e}")
        _cleanup_job_temp_files(job_id)
        await notify_job_update(
            job_id,
            stage_num=0,
            progress=0,
            message=f"Failed: {str(e)}",
            status="FAILED",
            error=str(e)
        )


# --- REST Endpoints ---
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "3.1.0",
        "tts_engine": "sarvam-bulbul-v3",
        "supported_speeds": ALLOWED_SPEEDS,
        "ffmpeg": settings.FFMPEG_PATH,
        "ffmpeg_detected": Path(settings.FFMPEG_PATH).exists() or bool(settings.FFMPEG_PATH),
        "active_jobs_count": sum(1 for j in JOBS.values() if j.get("status") == "PROCESSING")
    }


@app.get("/api/voices")
async def list_sarvam_voices():
    return {"model": "bulbul:v3", "voices": SARVAM_VOICES}


@app.post("/api/recap/generate")
async def start_recap_job(
    req: CreateRecapRequest,
    background_tasks: BackgroundTasks,
    x_sarvam_key: Optional[str] = Header(default=None, alias="X-Sarvam-Key")
):
    job_id = str(uuid.uuid4())[:8]
    speed = _normalize_speed(req.playback_speed)

    JOBS[job_id] = {
        "id": job_id,
        "url": req.url,
        "target_minutes": req.target_minutes,
        "story_style": req.story_style,
        "voice_speaker": req.voice_speaker,
        "playback_speed": speed,
        "status": "PROCESSING",
        "stage": 1,
        "progress": 5,
        "message": f"Initializing Sarvam AI studio ({speed:g}x speed)...",
        "created_at": asyncio.get_event_loop().time(),
    }
    JOB_EVENT_QUEUES[job_id] = []

    background_tasks.add_task(
        process_recap_pipeline,
        job_id=job_id,
        url=req.url,
        target_minutes=req.target_minutes,
        story_style=req.story_style,
        voice_speaker=req.voice_speaker,
        playback_speed=speed,
        sarvam_key=x_sarvam_key or settings.SARVAM_API_KEY
    )

    return {"job_id": job_id, "status": "QUEUED", "playback_speed": speed}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}/events")
async def stream_job_events(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = asyncio.Queue()
    JOB_EVENT_QUEUES.setdefault(job_id, []).append(queue)

    async def event_generator():
        yield {"event": "status", "data": json.dumps(JOBS[job_id])}
        try:
            while True:
                data = await queue.get()
                yield {"event": "status", "data": data}
                try:
                    parsed = json.loads(data)
                    if parsed.get("status") in ("COMPLETED", "FAILED"):
                        break
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass
        finally:
            if job_id in JOB_EVENT_QUEUES and queue in JOB_EVENT_QUEUES[job_id]:
                JOB_EVENT_QUEUES[job_id].remove(queue)

    return EventSourceResponse(event_generator())


@app.api_route("/api/download/{filename}", methods=["GET", "HEAD"])
async def download_export_file(filename: str):
    safe_name = Path(filename).name
    file_path = EXPORTS_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    if safe_name.endswith(".mp4"):
        media_type = "video/mp4"
    elif safe_name.endswith(".m4a"):
        media_type = "audio/mp4"
    else:
        media_type = "text/plain; charset=utf-8"
    return FileResponse(path=str(file_path), media_type=media_type, filename=safe_name)


@app.post("/api/recap/{job_id}/script/update")
async def update_script(job_id: str, req: UpdateScriptRequest):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    JOBS[job_id]["segments"] = req.segments
    script_file = SCRIPTS_DIR / f"script_{job_id}.json"
    with open(script_file, "w", encoding="utf-8") as f:
        json.dump(req.segments, f, indent=2, ensure_ascii=False)

    voice_mixer.generate_viral_subtitles(req.segments, job_id)
    return {"status": "SUCCESS", "message": "Script & SRT updated successfully"}


@app.post("/api/recap/{job_id}/voice/record")
async def record_user_voiceover(
    job_id: str,
    audio_file: UploadFile = File(...),
    game_volume: float = Form(0.15)
):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    job = JOBS[job_id]
    base_video = EXPORTS_DIR / f"final_recap_{job_id}.mp4"
    if not base_video.exists():
        raise HTTPException(status_code=400, detail="Master video not found")

    safe_ext = Path(audio_file.filename or "voice.webm").suffix or ".webm"
    user_audio_path = AUDIO_DIR / f"user_voice_{job_id}{safe_ext}"
    with open(user_audio_path, "wb") as f:
        f.write(await audio_file.read())

    final_filename = f"final_custom_recap_{job_id}.mp4"
    async with RENDER_SEMAPHORE:
        await voice_mixer.mix_custom_voiceover(
            stitched_video_path=str(base_video),
            user_voice_path=str(user_audio_path),
            output_filename=final_filename,
            game_volume=game_volume
        )

    final_url = f"/storage/exports/{final_filename}"
    job["final_video_url"] = final_url
    job["voice_mode"] = "SELF_RECORDED"

    return {
        "status": "SUCCESS",
        "final_video_url": final_url,
        "message": "Voiceover mixed successfully!"
    }
