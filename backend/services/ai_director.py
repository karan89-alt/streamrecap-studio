import asyncio
import json
import logging
import os
import re
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional

from config import settings

logger = logging.getLogger("streamrecap.director")

GEMINI_VISION_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.1-flash-lite-preview:generateContent"
)

STYLE_GUIDES: Dict[str, str] = {
    "Funny Storytelling": (
        "PURE COMEDY & ROAST in Hindi/Hinglish. Crack witty jokes, playful roasts, sarcastic punchlines, "
        "and hilarious observations strictly about what is VISUALLY happening in each clip frame and transcript. "
        "Do NOT include dry facts; focus 100% on humor and entertainment."
    ),
    "Facts Storytelling": (
        "MIND-BLOWING FACTS & HIDDEN DETAILS in Hindi/Hinglish. Share fascinating real-world facts, hidden visual details, "
        "behind-the-scenes trivia, or clever observations strictly connected to what is ACTUALLY visible in this video and clip. "
        "Do NOT do comedy roasts; focus 100% on sharp, intriguing facts."
    ),
    "Documentary Storytelling": (
        "AUTHORITATIVE DOCUMENTARY NARRATION (like National Geographic / Netflix) in crisp Hindi/Hinglish. "
        "Describe the real events unfolding on screen with gravitas, context, and depth."
    ),
    "Mystery & Suspense Storytelling": (
        "GRIPPING THRILLER & SUSPENSE narration in Hindi/Hinglish. Build curiosity, tension, and dramatic anticipation "
        "around the exact visuals and moments happening in each clip."
    ),
    "Investigative Storytelling": (
        "FORENSIC INVESTIGATIVE BREAKDOWN in Hindi/Hinglish. Point out specific visual clues, exact actions, "
        "turning points, and details visible right inside each clip frame."
    ),
    "Cinematic Storytelling": (
        "BLOCKBUSTER MOVIE-STYLE CINEMATIC narration in Hindi/Hinglish. Describe the visuals, lighting, movement, "
        "and emotion in each clip like an epic film trailer or dramatic scene."
    ),
    "Chronological Storytelling": (
        "CLEAR STEP-BY-STEP TIMELINE narration in Hindi/Hinglish ('Sabse pehle...', 'Iske baad...', 'Phir...'). "
        "Walk the viewer smoothly through the exact chronological progression of what happens in each clip."
    ),
    "Case Study Storytelling": (
        "ANALYTICAL CASE STUDY BREAKDOWN in Hindi/Hinglish. Break down the strategy, execution, decisions, "
        "cause-and-effect, and practical takeaways directly from what is shown in each clip."
    ),
    "Explainer Storytelling": (
        "ENGAGING YOUTUBE EXPLAINER in Hindi/Hinglish. Clearly and energetically explain to the viewer exactly "
        "what is happening in each clip, why it matters, and what happens next."
    ),
}


def _get_style_instruction(story_style: str) -> str:
    if story_style in STYLE_GUIDES:
        return STYLE_GUIDES[story_style]
    s = story_style.lower()
    if "fact" in s and "funny" not in s:
        return STYLE_GUIDES["Facts Storytelling"]
    if "funny" in s or "roast" in s:
        return STYLE_GUIDES["Funny Storytelling"]
    if "documentary" in s:
        return STYLE_GUIDES["Documentary Storytelling"]
    if "mystery" in s or "suspense" in s:
        return STYLE_GUIDES["Mystery & Suspense Storytelling"]
    if "investigative" in s:
        return STYLE_GUIDES["Investigative Storytelling"]
    if "cinematic" in s:
        return STYLE_GUIDES["Cinematic Storytelling"]
    if "chronological" in s:
        return STYLE_GUIDES["Chronological Storytelling"]
    if "case study" in s:
        return STYLE_GUIDES["Case Study Storytelling"]
    return STYLE_GUIDES["Explainer Storytelling"]


class AIDirector:
    """
    Multimodal Vision-First AI Director (v4.0.0):
    1. Literally WATCHES every extracted video clip (via 480px JPEG frames) + reads the real YouTube transcript.
    2. Understands ANY video topic (vlogs, movies, tech, animation, podcasts, documentaries, gaming, sports, etc.)
       with ZERO hardcoded GTA assumptions.
    3. Writes a cohesive 3-Act Hindi/Hinglish voiceover script strictly tailored to the chosen Storytelling Style
       and matched 1-to-1 to every clip's real on-screen action.
    """

    def __init__(self):
        self.gemini_key = (settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY") or "").strip()

    async def write_vision_script_from_clips(
        self,
        stream_meta: Dict[str, Any],
        clip_infos: List[Dict[str, Any]],
        story_style: str = "Explainer Storytelling",
        playback_speed: float = 1.0,
        gemini_key: Optional[str] = None,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """
        Watches ALL extracted clip frames in parallel batches via Gemini 3.1 Flash-Lite Vision
        and returns a scene-accurate, style-matched Hindi/Hinglish script for every clip.
        """
        key = (gemini_key or self.gemini_key or "").strip()
        total_clips = len(clip_infos)
        if total_clips == 0:
            return {"segments": [], "vision_used": False, "engine": "empty"}

        # Build a concise full-video overview from transcript so every batch understands the full story
        full_transcript = stream_meta.get("transcript") or []
        overview_snippets = self._build_video_overview(full_transcript)

        batch_size = 12
        batches: List[List[Dict[str, Any]]] = [
            clip_infos[i : i + batch_size] for i in range(0, total_clips, batch_size)
        ]

        vision_results: Dict[int, Dict[str, Any]] = {}
        vision_batches_ok = 0

        if key:
            sem = asyncio.Semaphore(3)
            completed_batches = 0

            async def _run_batch(b_idx: int, batch: List[Dict[str, Any]]):
                nonlocal completed_batches, vision_batches_ok
                async with sem:
                    try:
                        items = await asyncio.wait_for(
                            asyncio.to_thread(
                                self._call_gemini_vision_batch_sync,
                                key,
                                stream_meta,
                                overview_snippets,
                                batch,
                                total_clips,
                                story_style,
                                playback_speed,
                            ),
                            timeout=30.0,
                        )
                        if items:
                            vision_batches_ok += 1
                            for item in items:
                                c_idx = int(item.get("clip_index", -1))
                                if c_idx >= 0:
                                    vision_results[c_idx] = item
                    except Exception as e:
                        logger.warning(f"Gemini Vision batch {b_idx + 1}/{len(batches)} error: {e}")
                    finally:
                        completed_batches += 1
                        if progress_callback:
                            await progress_callback(completed_batches, len(batches))

            await asyncio.gather(*[_run_batch(i, b) for i, b in enumerate(batches)])
        else:
            logger.warning("No GEMINI_API_KEY configured; using topic-neutral transcript fallback.")

        # Assemble final ordered segments (1-to-1 with clip_infos)
        segments: List[Dict[str, Any]] = []
        speed = max(1.0, min(2.0, float(playback_speed)))
        est_dur = round(max(3.6, 6.5 / speed), 2)
        running_t = 0.0

        for pos, clip in enumerate(clip_infos):
            c_idx = int(clip["clip_index"])
            act_label = self._act_for_position(pos, total_clips)
            ai_item = vision_results.get(c_idx)

            if ai_item and str(ai_item.get("dialogue_hindi", "")).strip():
                dialogue = self._clean_dialogue(str(ai_item["dialogue_hindi"]))
                scene_note = str(ai_item.get("visual_summary") or ai_item.get("scene_note") or "").strip()
                if not scene_note:
                    scene_note = f"Clip {pos + 1} ({clip['vod_start_fmt']})"
                act_name = str(ai_item.get("act") or act_label).strip() or act_label
                pacing = str(ai_item.get("pacing") or ("energetic_hook" if pos == 0 else "story_flow")).strip()
            else:
                # Topic-neutral fallback using REAL video title & transcript (ZERO hardcoded GTA!)
                dialogue, scene_note = self._topic_neutral_fallback_line(
                    stream_meta=stream_meta,
                    clip=clip,
                    pos=pos,
                    total=total_clips,
                    story_style=story_style,
                )
                act_name = act_label
                pacing = "energetic_hook" if pos == 0 else ("satisfying_payoff" if pos == total_clips - 1 else "story_flow")

            v_start = running_t
            v_end = running_t + est_dur
            running_t = v_end

            segments.append({
                "id": f"seg_{pos + 1:03d}",
                "clip_index": pos,
                "source_clip_index": c_idx,
                "clip_path": clip.get("clip_path", ""),
                "act": act_name,
                "video_start": round(v_start, 2),
                "video_end": round(v_end, 2),
                "duration": est_dur,
                "video_start_fmt": self._fmt_time(v_start),
                "video_end_fmt": self._fmt_time(v_end),
                "vod_start": round(float(clip["vod_start"]), 2),
                "vod_end": round(float(clip["vod_end"]), 2),
                "vod_start_fmt": clip.get("vod_start_fmt") or self._fmt_time(float(clip["vod_start"])),
                "vod_end_fmt": clip.get("vod_end_fmt") or self._fmt_time(float(clip["vod_end"])),
                "scene_note": scene_note[:140],
                "dialogue_hindi": dialogue,
                "pacing": pacing,
                "word_count": len(dialogue.split()),
                "vision_matched": bool(ai_item),
            })

        vision_used = vision_batches_ok > 0
        logger.info(
            f"Vision Script complete: {len(segments)} clips | "
            f"vision_matched={sum(1 for s in segments if s['vision_matched'])}/{len(segments)} | "
            f"style='{story_style}'"
        )
        return {
            "segments": segments,
            "vision_used": vision_used,
            "engine": "gemini-3.1-flash-lite-vision" if vision_used else "transcript-neutral-fallback",
        }

    def _call_gemini_vision_batch_sync(
        self,
        api_key: str,
        stream_meta: Dict[str, Any],
        overview_snippets: str,
        batch: List[Dict[str, Any]],
        total_clips: int,
        story_style: str,
        playback_speed: float,
    ) -> List[Dict[str, Any]]:
        """
        Sends up to 12 real video clip frames (480px JPEG) + transcripts + full-video metadata
        to Gemini 3.1 Flash-Lite Vision and gets back strict JSON scene-accurate Hindi script lines.
        """
        title = stream_meta.get("title") or "YouTube Video"
        channel = stream_meta.get("channel") or "Creator"
        duration = int(stream_meta.get("duration") or 0)
        description = (stream_meta.get("description") or "")[:450].replace("\n", " ")
        style_guide = _get_style_instruction(story_style)

        first_idx = int(batch[0]["clip_index"])
        last_idx = int(batch[-1]["clip_index"])
        is_opening_batch = first_idx == 0
        is_ending_batch = last_idx >= total_clips - 1

        arc_hint = []
        if is_opening_batch:
            arc_hint.append(
                "- Clip 0 MUST be an energetic, advertiser-safe 0-7s opening hook introducing the REAL video topic and hooking the viewer."
            )
        if is_ending_batch:
            arc_hint.append(
                f"- Clip {total_clips - 1} MUST be a crisp, satisfying finale/outro wrapping up what actually happened in the video with a brief like/subscribe CTA."
            )
        arc_hint_str = "\n".join(arc_hint) if arc_hint else "- Maintain smooth story continuity matching each clip's exact visual progression."

        intro_prompt = f"""You are a top Indian YouTube Video Editor & Hindi/Hinglish Scriptwriter.
You are literally WATCHING the actual extracted frames of a YouTube video so you can write a 100% accurate, scene-matched Hindi/Hinglish voiceover.

FULL VIDEO CONTEXT:
- Video Title: {title}
- Channel / Creator: {channel}
- Total Video Length: {self._fmt_time(duration)}
- Description excerpt: {description}
- Full-video transcript highlights: {overview_snippets or "Visual/non-verbal video — rely closely on the clip frames below."}

SELECTED STORYTELLING STYLE: {story_style}
STYLE DIRECTION: {style_guide}

STRICT RULES (NEVER BREAK THESE):
1. ZERO HALLUCINATION: Watch each clip's attached image frame carefully and read its transcript excerpt. Talk ONLY about what is ACTUALLY happening in THIS video and THAT exact frame! NEVER invent unrelated topics (for example, NEVER mention GTA, police, or gaming unless the video frames literally show GTA!).
2. EXACT VISUAL SYNC: Every single clip's `dialogue_hindi` must directly describe, react to, or explain what is visible in THAT clip's image frame (characters, animals, people, objects, setting, expressions, actions, on-screen text).
3. WORD COUNT FOR VOICEOVER: Write 14 to 19 natural spoken words per clip in Roman-script Hindi/Hinglish (e.g. "Dekhiye kaise...", "Yahan scene bilkul badal jata hai..."). This will be spoken aloud by an Indian TTS voice actor at {playback_speed:g}x speed, so keep sentences punchy, natural, and easy to pronounce.
4. NO MARKDOWN OR EMOJIS: Plain spoken text only in `dialogue_hindi` (no asterisks, no hashtags, no emojis, no bullet points).
5. STORY ARC (Total clips in full video: {total_clips}; this batch covers clips {first_idx} to {last_idx}):
{arc_hint_str}

Return ONLY a valid JSON array with ONE object per clip in this exact batch, matching these exact keys:
[
  {{
    "clip_index": <int matching the clip number below>,
    "act": "<short act label, e.g. Act I: Hook / Act II: Main Story / Act III: Finale>",
    "visual_summary": "<brief 5-10 word description of what you literally see in this clip's image>",
    "dialogue_hindi": "<14-19 words of natural Roman-script Hindi/Hinglish narration matching this exact clip in {story_style} style>",
    "pacing": "<energetic_hook | suspense_building | fast_paced | funny_punchline | informative | satisfying_payoff>"
  }}
]

Now inspect each clip below in order:"""

        parts: List[Dict[str, Any]] = [{"text": intro_prompt}]

        for clip in batch:
            c_idx = int(clip["clip_index"])
            v_start = clip.get("vod_start_fmt") or self._fmt_time(float(clip["vod_start"]))
            v_end = clip.get("vod_end_fmt") or self._fmt_time(float(clip["vod_end"]))
            tr = (clip.get("transcript_excerpt") or "").strip()
            tr_note = f'Spoken audio: "{tr}"' if tr else "Spoken audio: (visual scene / background sound)"

            parts.append({
                "text": f"\n--- CLIP {c_idx} (Video time {v_start} - {v_end}) | {tr_note} ---"
            })
            frame_b64 = clip.get("frame_b64")
            if frame_b64:
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": frame_b64,
                    }
                })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.65,
                "responseMimeType": "application/json",
            },
        }

        url = f"{GEMINI_VISION_ENDPOINT}?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        last_err = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=28) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                raw_text = (
                    body.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                )
                parsed = self._parse_json_array(raw_text)
                if parsed:
                    return parsed
            except urllib.error.HTTPError as he:
                err_body = he.read().decode("utf-8", errors="ignore")[:240]
                last_err = f"HTTP {he.code}: {err_body}"
                logger.warning(f"Gemini Vision HTTP error (attempt {attempt + 1}): {last_err}")
                if he.code in (400, 401, 403):
                    break
            except Exception as e:
                last_err = str(e)
                logger.warning(f"Gemini Vision call failed (attempt {attempt + 1}): {e}")

        if last_err:
            logger.error(f"Gemini Vision batch failed after retries: {last_err}")
        return []

    @staticmethod
    def _parse_json_array(raw_text: str) -> List[Dict[str, Any]]:
        if not raw_text:
            return []
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, list):
                        return [x for x in v if isinstance(x, dict)]
        except Exception:
            m = re.search(r"\[.*\]", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                    if isinstance(data, list):
                        return [x for x in data if isinstance(x, dict)]
                except Exception:
                    pass
        return []

    @staticmethod
    def _clean_dialogue(text: str) -> str:
        text = re.sub(r"[*_`#]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _build_video_overview(transcript: List[Dict[str, Any]]) -> str:
        if not transcript:
            return ""
        n = len(transcript)
        sample_indices = sorted(set(int(i * (n - 1) / min(14, max(1, n - 1))) for i in range(min(15, n))))
        snippets = [transcript[i]["text"] for i in sample_indices if transcript[i].get("text")]
        return " ... ".join(snippets)[:900]

    @staticmethod
    def _act_for_position(pos: int, total: int) -> str:
        if pos == 0:
            return "Act I: The Hook"
        ratio = pos / max(1, total - 1)
        if ratio < 0.22:
            return "Act I: Setup"
        if ratio < 0.80:
            return "Act II: Main Story"
        if pos == total - 1:
            return "Act III: Finale"
        return "Act III: Climax"

    def _topic_neutral_fallback_line(
        self,
        stream_meta: Dict[str, Any],
        clip: Dict[str, Any],
        pos: int,
        total: int,
        story_style: str,
    ) -> tuple[str, str]:
        """Topic-neutral fallback using REAL video metadata & transcript (zero hardcoded GTA!)."""
        title = (stream_meta.get("title") or "is video")[:55]
        channel = stream_meta.get("channel") or "creator"
        ts = clip.get("vod_start_fmt") or "00:00"
        tr = (clip.get("transcript_excerpt") or "").strip()

        if pos == 0:
            return (
                f"Dosto aaj hum {channel} ke video {title} ka sabse zabardast recap dekhne wale hain!",
                f"Opening hook for {title}",
            )
        if pos == total - 1:
            return (
                f"Yeh tha {title} ka poora safar — aapko sabse best moment kaunsa laga, comment me zaroor batayein!",
                "Video finale and outro",
            )
        if tr:
            short_tr = " ".join(tr.split()[:10])
            return (
                f"Video ke {ts} par bahut interesting moment aata hai jahan baat ho rahi hai: {short_tr}.",
                f"Scene at {ts}: {short_tr}",
            )
        return (
            f"Ab video ke {ts} wale scene ko dhyan se dekhiye, yahan se poori kahani ek naya mod leti hai!",
            f"Key visual moment at {ts}",
        )

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        s = max(0, int(seconds))
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"
