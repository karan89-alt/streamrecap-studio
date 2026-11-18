import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
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
from services.video_stitcher import VideoStitcher
from services.voice_mixer import VoiceMixer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("streamrecap.api")

app = FastAPI(
    title="StreamRecap Studio API",
    description="Transforms long YouTube gaming live streams into edited Full HD Hindi movie-explainer recaps",
    version="2.0.0"
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static storage directory to serve stitched videos, exports, and subtitles
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

# In-memory jobs store
JOBS: Dict[str, Dict[str, Any]] = {}
JOB_EVENT_QUEUES: Dict[str, List[asyncio.Queue]] = {}

# Guard heavy FFmpeg rendering so cloud containers never OOM
RENDER_SEMAPHORE = asyncio.Semaphore(1)

extractor = YouTubeExtractor()
director = AIDirector()
stitcher = VideoStitcher()
voice_mixer = VoiceMixer()


# --- Models ---
class CreateRecapRequest(BaseModel):
    url: str
    target_minutes: int = 15
    story_style: str = "Explainer Storytelling"


class UpdateScriptRequest(BaseModel):
    segments: List[Dict[str, Any]]


def _fmt_mmss(secs: float) -> str:
    s = max(0, int(secs))
    return f"{s // 60:02d}:{s % 60:02d}"


def _cleanup_job_temp_files(job_id: str):
    """Remove temporary clip chunks after export to keep cloud storage clean."""
    try:
        for p in CLIPS_DIR.glob(f"clip_{job_id}_*.mp4"):
            p.unlink(missing_ok=True)
        for p in TEMP_DIR.glob(f"*{job_id}*"):
            p.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Cleanup warning for {job_id}: {e}")


async def notify_job_update(job_id: str, stage_num: int, progress: int, message: str, **extra):
    """Pushes real-time SSE updates to connected frontend clients."""
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


# --- Background Worker Pipeline ---
async def process_recap_pipeline(job_id: str, url: str, target_minutes: int, story_style: str):
    try:
        target_minutes = max(1, min(30, int(target_minutes)))
        target_seconds = target_minutes * 60

        # Step 1: Fetch metadata & hype spikes
        await notify_job_update(
            job_id,
            stage_num=1,
            progress=12,
            message="Analyzing stream & detecting peak moments..."
        )

        metadata = await extractor.get_stream_metadata(url)
        stream_duration = float(metadata.get("duration") or 3000)
        hype_spikes = await extractor.detect_hype_spikes(metadata, target_minutes)

        await notify_job_update(
            job_id,
            stage_num=1,
            progress=25,
            message=f"Found {len(hype_spikes)} highlights in '{metadata.get('title', 'Stream')[:40]}'",
            metadata=metadata
        )

        # Step 2: AI Script & Scene Selection
        await notify_job_update(
            job_id,
            stage_num=2,
            progress=35,
            message=f"Writing script in {story_style} style..."
        )

        script_segments = await director.create_story_and_script(
            stream_meta=metadata,
            hype_spikes=hype_spikes,
            target_minutes=target_minutes,
            story_style=story_style
        )

        await notify_job_update(
            job_id,
            stage_num=2,
            progress=48,
            message=f"Script ready ({len(script_segments)} scenes). Extracting video clips...",
            segments=script_segments
        )

        # Step 3: Fast partial clip downloads (2 concurrent workers to prevent YouTube IP throttling)
        total_clips = len(script_segments)
        completed_downloads = 0
        dl_sem = asyncio.Semaphore(2)

        # Pre-warm direct stream URL once before parallel workers start
        await extractor.get_direct_stream_url(metadata.get("url", url))

        async def _download_one(idx: int, seg: Dict[str, Any]):
            nonlocal completed_downloads
            clip_filename = f"clip_{job_id}_{idx:03d}.mp4"
            async with dl_sem:
                clip_path = await extractor.download_section(
                    url=metadata.get("url", url),
                    start_sec=seg["vod_start"],
                    end_sec=seg["vod_end"],
                    output_filename=clip_filename,
                    max_duration=stream_duration
                )
                completed_downloads += 1
                await notify_job_update(
                    job_id,
                    stage_num=3,
                    progress=48 + int((completed_downloads / max(1, total_clips)) * 30),
                    message=f"Extracted clip {completed_downloads}/{total_clips}..."
                )
                return idx, clip_path

        tasks = [_download_one(idx, seg) for idx, seg in enumerate(script_segments)]
        results = await asyncio.gather(*tasks)
        results.sort(key=lambda x: x[0])

        # Step 3b: Measure EXACT real duration of every extracted clip & resync timestamps!
        synced_clip_paths: List[str] = []
        synced_segments: List[Dict[str, Any]] = []
        cumulative_time = 0.0

        for idx, clip_path in results:
            if not clip_path or not Path(clip_path).exists():
                continue

            real_dur = await extractor.get_clip_duration(clip_path)
            if real_dur < 1.0:
                continue

            # Keep total video tightly matched to requested target duration
            if cumulative_time > 0 and (cumulative_time + real_dur) > (target_seconds + 12):
                break

            seg = dict(script_segments[idx])
            seg["clip_index"] = len(synced_segments)
            seg["id"] = f"seg_{len(synced_segments) + 1:03d}"
            seg["video_start"] = round(cumulative_time, 2)
            seg["video_end"] = round(cumulative_time + real_dur, 2)
            seg["duration"] = round(real_dur, 2)
            seg["video_start_fmt"] = _fmt_mmss(cumulative_time)
            seg["video_end_fmt"] = _fmt_mmss(cumulative_time + real_dur)

            cumulative_time += real_dur
            synced_clip_paths.append(clip_path)
            synced_segments.append(seg)

        if not synced_clip_paths:
            raise RuntimeError(
                "Could not extract video clips from this YouTube URL. "
                "The video may be private, region-locked, or blocked. Try another public YouTube VOD link."
            )

        # Persist synced script JSON
        script_file = SCRIPTS_DIR / f"script_{job_id}.json"
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(synced_segments, f, indent=2, ensure_ascii=False)

        # Stitch clips & render Full HD under concurrency semaphore to protect RAM/CPU
        async with RENDER_SEMAPHORE:
            await notify_job_update(
                job_id,
                stage_num=3,
                progress=82,
                message=f"Stitching {len(synced_clip_paths)} clips ({_fmt_mmss(cumulative_time)} total)...",
                segments=synced_segments
            )

            stitched_filename = f"recap_master_{job_id}.mp4"
            stitched_path = await stitcher.process_and_stitch_clips(
                clip_paths=synced_clip_paths,
                output_filename=stitched_filename,
                job_id=job_id
            )
            stitched_url = f"/storage/exports/{stitched_filename}"

            # Step 4: Render Full HD 1080p Video with Viral Font Subtitles + Original Audio
            await notify_job_update(
                job_id,
                stage_num=4,
                progress=90,
                message="Rendering 1080p Full HD video with viral captions..."
            )

            subtitle_files = voice_mixer.generate_viral_subtitles(
                script_segments=synced_segments,
                job_id=job_id
            )

            final_filename = f"final_recap_{job_id}.mp4"
            await voice_mixer.render_full_hd_recap(
                stitched_video_path=stitched_path,
                ass_subtitles_path=subtitle_files["ass_path"],
                output_filename=final_filename
            )

        final_url = f"/storage/exports/{final_filename}"
        srt_url = f"/storage/exports/subtitles_{job_id}.srt"

        # Clean up intermediate clip fragments
        _cleanup_job_temp_files(job_id)

        # Step 5: Completed!
        await notify_job_update(
            job_id,
            stage_num=5,
            progress=100,
            message="Full HD Recap & Synchronized Script Ready!",
            status="COMPLETED",
            final_video_url=final_url,
            stitched_video_url=stitched_url,
            game_audio_video_url=stitched_url,
            srt_url=srt_url,
            segments=synced_segments,
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
        "ffmpeg": settings.FFMPEG_PATH,
        "ffmpeg_detected": Path(settings.FFMPEG_PATH).exists() or bool(settings.FFMPEG_PATH),
        "active_jobs_count": sum(1 for j in JOBS.values() if j.get("status") == "PROCESSING")
    }


@app.post("/api/recap/generate")
async def start_recap_job(req: CreateRecapRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())[:8]

    JOBS[job_id] = {
        "id": job_id,
        "url": req.url,
        "target_minutes": req.target_minutes,
        "story_style": req.story_style,
        "status": "PROCESSING",
        "stage": 1,
        "progress": 5,
        "message": "Initializing video recap engine...",
        "created_at": asyncio.get_event_loop().time(),
    }
    JOB_EVENT_QUEUES[job_id] = []

    background_tasks.add_task(
        process_recap_pipeline,
        job_id=job_id,
        url=req.url,
        target_minutes=req.target_minutes,
        story_style=req.story_style,
    )

    return {"job_id": job_id, "status": "QUEUED"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}/events")
async def stream_job_events(job_id: str):
    """Server-Sent Events endpoint for real-time job updates."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = asyncio.Queue()
    JOB_EVENT_QUEUES.setdefault(job_id, []).append(queue)

    async def event_generator():
        initial = JOBS[job_id]
        yield {"event": "status", "data": json.dumps(initial)}

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
    """Forces direct browser file download with Content-Disposition attachment header."""
    safe_name = Path(filename).name
    file_path = EXPORTS_DIR / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Export file not found")
    media_type = "video/mp4" if safe_name.endswith(".mp4") else "text/plain; charset=utf-8"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=safe_name
    )


@app.post("/api/recap/{job_id}/script/update")
async def update_script(job_id: str, req: UpdateScriptRequest):
    """Allows user to edit and save updated Hindi dialogue lines and updates .srt immediately."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    JOBS[job_id]["segments"] = req.segments

    script_file = SCRIPTS_DIR / f"script_{job_id}.json"
    with open(script_file, "w", encoding="utf-8") as f:
        json.dump(req.segments, f, indent=2, ensure_ascii=False)

    # Also regenerate SRT file so downloaded subtitles match edits
    voice_mixer.generate_viral_subtitles(req.segments, job_id)

    return {"status": "SUCCESS", "message": "Script & SRT updated successfully"}


@app.post("/api/recap/{job_id}/voice/record")
async def record_user_voiceover(
    job_id: str,
    audio_file: UploadFile = File(...),
    game_volume: float = Form(0.15)
):
    """Teleprompter Voiceover Recording Upload & Auto-Mix (preserves viral captions)."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    job = JOBS[job_id]
    # Prefer mixing over the burned-in caption video so captions stay visible!
    base_video = EXPORTS_DIR / f"final_recap_{job_id}.mp4"
    if not base_video.exists():
        base_video = EXPORTS_DIR / f"recap_master_{job_id}.mp4"
    if not base_video.exists():
        raise HTTPException(status_code=400, detail="Master video not found")

    safe_ext = Path(audio_file.filename or "voice.webm").suffix or ".webm"
    user_audio_path = AUDIO_DIR / f"user_voice_{job_id}{safe_ext}"
    with open(user_audio_path, "wb") as f:
        content = await audio_file.read()
        f.write(content)

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
        "message": "Voiceover mixed with ducked game audio successfully!"
    }
