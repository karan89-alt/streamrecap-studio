import asyncio
import json
import logging
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from config import (
    settings,
    STORAGE_DIR,
    CLIPS_DIR,
    SCRIPTS_DIR,
    AUDIO_DIR,
    EXPORTS_DIR,
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
    version="1.0.0"
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static storage directory to serve stitched videos, clips, audio, and exports
app.mount("/storage", StaticFiles(directory=str(STORAGE_DIR)), name="storage")

# In-memory jobs database
JOBS: Dict[str, Dict[str, Any]] = {}
JOB_EVENT_QUEUES: Dict[str, List[asyncio.Queue]] = {}

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
        "stage": stage_num,
        "progress": progress,
        "message": message,
        **extra
    }

    if job_id in JOB_EVENT_QUEUES:
        for q in JOB_EVENT_QUEUES[job_id]:
            await q.put(json.dumps(payload))


# --- Background Worker Pipeline ---
async def process_recap_pipeline(job_id: str, url: str, target_minutes: int, story_style: str):
    try:
        # Step 1: Fetch metadata & hype spikes
        await notify_job_update(
            job_id,
            stage_num=1,
            progress=15,
            message="Analyzing stream & detecting peak moments..."
        )

        metadata = await extractor.get_stream_metadata(url)
        hype_spikes = await extractor.detect_hype_spikes(metadata, target_minutes)

        await notify_job_update(
            job_id,
            stage_num=1,
            progress=30,
            message=f"Detected {len(hype_spikes)} action spikes. Structuring story arc...",
            metadata=metadata
        )

        # Step 2: AI Script & Scene Selection
        await notify_job_update(
            job_id,
            stage_num=2,
            progress=40,
            message=f"Writing script in {story_style} style..."
        )

        script_segments = await director.create_story_and_script(
            stream_meta=metadata,
            hype_spikes=hype_spikes,
            target_minutes=target_minutes,
            story_style=story_style
        )

        # Save script JSON
        script_file = SCRIPTS_DIR / f"script_{job_id}.json"
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(script_segments, f, indent=2, ensure_ascii=False)

        await notify_job_update(
            job_id,
            stage_num=2,
            progress=55,
            message=f"Script ready ({len(script_segments)} scenes). Extracting clips...",
            segments=script_segments
        )

        # Step 3: Fast partial section downloads in parallel workers & stitching
        total_clips = len(script_segments)
        completed_downloads = 0
        sem = asyncio.Semaphore(2)

        async def _download_one(idx: int, seg: Dict[str, Any]):
            nonlocal completed_downloads
            clip_filename = f"clip_{job_id}_{idx:03d}.mp4"
            async with sem:
                clip_path = await extractor.download_section(
                    url=metadata.get("url", url),
                    start_sec=seg["vod_start"],
                    end_sec=seg["vod_end"],
                    output_filename=clip_filename
                )
                completed_downloads += 1
                await notify_job_update(
                    job_id,
                    stage_num=3,
                    progress=55 + int((completed_downloads / total_clips) * 25),
                    message=f"Extracted clip {completed_downloads}/{total_clips}..."
                )
                return idx, clip_path

        tasks = [_download_one(idx, seg) for idx, seg in enumerate(script_segments)]
        results = await asyncio.gather(*tasks)
        results.sort(key=lambda x: x[0])
        clip_paths = [r[1] for r in results]

        # Stitch clips with anti-Content-ID scale/crop & in-game audio normalization
        await notify_job_update(
            job_id,
            stage_num=3,
            progress=85,
            message="Stitching 1080p Full HD video..."
        )

        stitched_filename = f"recap_master_{job_id}.mp4"
        stitched_path = await stitcher.process_and_stitch_clips(
            clip_paths=clip_paths,
            output_filename=stitched_filename,
            job_id=job_id
        )

        stitched_url = f"/storage/exports/{stitched_filename}"

        # Step 4: Render Full HD Video with Viral Font Subtitles + Original Game Audio
        await notify_job_update(
            job_id,
            stage_num=4,
            progress=92,
            message="Burning viral captions onto 1080p video..."
        )

        subtitle_files = voice_mixer.generate_viral_subtitles(
            script_segments=script_segments,
            job_id=job_id
        )

        final_filename = f"final_recap_{job_id}.mp4"
        final_video_path = await voice_mixer.render_full_hd_recap(
            stitched_video_path=stitched_path,
            ass_subtitles_path=subtitle_files["ass_path"],
            output_filename=final_filename
        )

        final_url = f"/storage/exports/{final_filename}"
        srt_url = f"/storage/exports/subtitles_{job_id}.srt"

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
            segments=script_segments,
            metadata=metadata
        )

    except Exception as e:
        logger.exception(f"Pipeline error for job {job_id}: {e}")
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
        "active_jobs_count": len(JOBS)
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
    """Server-Sent Events endpoint for zero-latency client state synchronization."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    queue = asyncio.Queue()
    if job_id not in JOB_EVENT_QUEUES:
        JOB_EVENT_QUEUES[job_id] = []
    JOB_EVENT_QUEUES[job_id].append(queue)

    async def event_generator():
        initial = JOBS[job_id]
        yield {"event": "status", "data": json.dumps(initial)}

        try:
            while True:
                data = await queue.get()
                yield {"event": "status", "data": data}
        except asyncio.CancelledError:
            pass
        finally:
            if job_id in JOB_EVENT_QUEUES and queue in JOB_EVENT_QUEUES[job_id]:
                JOB_EVENT_QUEUES[job_id].remove(queue)

    return EventSourceResponse(event_generator())


@app.post("/api/recap/{job_id}/script/update")
async def update_script(job_id: str, req: UpdateScriptRequest):
    """Allows user to edit and save updated Hindi dialogue lines."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    JOBS[job_id]["segments"] = req.segments

    # Persist updated script file
    script_file = SCRIPTS_DIR / f"script_{job_id}.json"
    with open(script_file, "w", encoding="utf-8") as f:
        json.dump(req.segments, f, indent=2, ensure_ascii=False)

    return {"status": "SUCCESS", "message": "Script updated successfully"}


@app.post("/api/recap/{job_id}/voice/record")
async def record_user_voiceover(
    job_id: str,
    audio_file: UploadFile = File(...),
    game_volume: float = Form(0.15)
):
    """Option A: Teleprompter Voiceover Recording Upload & Auto-Mix"""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")

    job = JOBS[job_id]
    stitched_filename = f"recap_master_{job_id}.mp4"
    stitched_path = EXPORTS_DIR / stitched_filename

    if not stitched_path.exists():
        raise HTTPException(status_code=400, detail="Master stitched video not found")

    # Save uploaded voice audio
    user_audio_path = AUDIO_DIR / f"user_voice_{job_id}_{audio_file.filename}"
    with open(user_audio_path, "wb") as f:
        content = await audio_file.read()
        f.write(content)

    final_filename = f"final_custom_recap_{job_id}.mp4"
    final_video_path = await voice_mixer.mix_custom_voiceover(
        stitched_video_path=str(stitched_path),
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
