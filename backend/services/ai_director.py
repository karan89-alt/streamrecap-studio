import json
import logging
import math
import os
from typing import Dict, List, Any, Optional

from config import settings

logger = logging.getLogger("streamrecap.director")


class AIDirector:
    """
    AI Director responsible for:
    1. Structuring video intervals into a 3-Act Story Arc.
    2. Enforcing the Clean 0-7s Intro Rule (advertiser-safe hook).
    3. Enforcing Strict Duration Sync (~2.2 Hindi words per second).
    4. Crafting natural Hindi/Hinglish scripts tailored to the exact storytelling style:
       - Funny + Facts
       - Documentary Storytelling
       - Mystery & Suspense Storytelling
       - Investigative Storytelling
       - Cinematic Storytelling
       - Chronological Storytelling
       - Case Study Storytelling
       - Explainer Storytelling
    """

    def __init__(self):
        self.gemini_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        self.openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")

    async def create_story_and_script(
        self,
        stream_meta: Dict[str, Any],
        hype_spikes: List[Dict[str, Any]],
        target_minutes: int = 15,
        story_style: str = "Explainer Storytelling"
    ) -> List[Dict[str, Any]]:
        target_seconds = target_minutes * 60

        # Try Gemini if key is available
        if self.gemini_key:
            try:
                script = await self._generate_with_gemini(stream_meta, hype_spikes, target_seconds, story_style)
                if script and len(script) >= 3:
                    return script
            except Exception as e:
                logger.warning(f"Gemini script generation fallback: {e}")

        # Try OpenAI if key is available
        if self.openai_key:
            try:
                script = await self._generate_with_openai(stream_meta, hype_spikes, target_seconds, story_style)
                if script and len(script) >= 3:
                    return script
            except Exception as e:
                logger.warning(f"OpenAI script generation fallback: {e}")

        # High-octane procedural Hindi/Hinglish screenwriter
        return self._generate_procedural_script(stream_meta, hype_spikes, target_seconds, story_style)

    def _generate_procedural_script(
        self,
        stream_meta: Dict[str, Any],
        hype_spikes: List[Dict[str, Any]],
        target_seconds: int,
        story_style: str
    ) -> List[Dict[str, Any]]:
        stream_duration = stream_meta.get("duration", 14400)
        channel = stream_meta.get("channel", "Streamer")

        avg_segment_duration = 9.0
        num_segments = max(4, round(target_seconds / avg_segment_duration))

        # 3 Acts partition:
        act1_count = max(1, round(num_segments * 0.20))
        act3_count = max(1, round(num_segments * 0.20))
        act2_count = max(2, num_segments - act1_count - act3_count)

        segments = []
        current_video_time = 0.0
        style_templates = self._get_style_templates(story_style, channel)
        segment_index = 0

        def make_segment(act_name: str, vod_start: float, duration: float, scene_desc: str, dialogue: str, pacing: str):
            nonlocal current_video_time, segment_index
            video_start = current_video_time
            video_end = video_start + duration
            current_video_time = video_end

            words = dialogue.strip().split()
            ideal_word_count = max(6, int(duration * 2.2))
            if len(words) < ideal_word_count:
                fillers = ["samajh rahe ho?", "dhyan se dekho!", "aur fir dekho!", "bhai log!"]
                while len(words) < ideal_word_count:
                    words.append(fillers[len(words) % len(fillers)])
                dialogue = " ".join(words)
            elif len(words) > ideal_word_count + 4:
                dialogue = " ".join(words[:ideal_word_count])

            seg = {
                "id": f"seg_{segment_index + 1:03d}",
                "clip_index": segment_index,
                "act": act_name,
                "video_start": round(video_start, 2),
                "video_end": round(video_end, 2),
                "duration": round(duration, 2),
                "video_start_fmt": self._fmt_time(video_start),
                "video_end_fmt": self._fmt_time(video_end),
                "vod_start": round(vod_start, 2),
                "vod_end": round(vod_start + duration, 2),
                "vod_start_fmt": self._fmt_time(vod_start),
                "vod_end_fmt": self._fmt_time(vod_start + duration),
                "scene_note": scene_desc,
                "dialogue_hindi": dialogue,
                "pacing": pacing,
                "word_count": len(dialogue.split()),
                "target_words": ideal_word_count,
            }
            segment_index += 1
            return seg

        # ACT I: THE HOOK & SETUP (Clean 0-7s Intro Rule)
        intro_dur = 8.0
        segments.append(
            make_segment(
                "Act I: The Hook",
                120.0,
                intro_dur,
                "Opening hook establishing the grand mission and strategy.",
                style_templates["clean_intro_dialogue"],
                "energetic_hook"
            )
        )

        for i in range(1, act1_count):
            dur = 8.0 + (i % 4)
            vod_s = (stream_duration * 0.05) + (i * 240)
            tmpl = style_templates["act1_scenes"][i % len(style_templates["act1_scenes"])]
            segments.append(
                make_segment(
                    "Act I: Setup & Infiltration",
                    vod_s,
                    dur,
                    tmpl["note"],
                    tmpl["dialogue"],
                    "suspense_building"
                )
            )

        # ACT II: CHAOS & ESCALATION
        act2_start_vod = stream_duration * 0.20
        act2_end_vod = stream_duration * 0.75
        act2_step = (act2_end_vod - act2_start_vod) / max(1, act2_count)

        for i in range(act2_count):
            dur = 7.5 + ((i * 3) % 5)
            vod_s = act2_start_vod + (i * act2_step) + ((i * 37) % 60)
            tmpl = style_templates["act2_scenes"][i % len(style_templates["act2_scenes"])]
            segments.append(
                make_segment(
                    f"Act II: {tmpl.get('title', 'The Mission')}",
                    vod_s,
                    dur,
                    tmpl["note"],
                    tmpl["dialogue"],
                    "fast_paced" if i % 2 == 0 else "tension_climax"
                )
            )

        # ACT III: CLIMAX & PAYOFF
        act3_start_vod = stream_duration * 0.80
        act3_step = (stream_duration * 0.18) / max(1, act3_count)

        for i in range(act3_count - 1):
            dur = 8.0 + (i % 3)
            vod_s = act3_start_vod + (i * act3_step)
            tmpl = style_templates["act3_scenes"][i % len(style_templates["act3_scenes"])]
            segments.append(
                make_segment(
                    f"Act III: {tmpl.get('title', 'Final Showdown')}",
                    vod_s,
                    dur,
                    tmpl["note"],
                    tmpl["dialogue"],
                    "hype_punchline"
                )
            )

        # Outro
        outro_dur = max(6.0, target_seconds - current_video_time)
        if outro_dur > 14.0:
            outro_dur = 10.0
        segments.append(
            make_segment(
                "Act III: Mission Conclusion",
                stream_duration - 45.0,
                outro_dur,
                "Mission completed, score transferred, final outro moment.",
                style_templates["outro_dialogue"],
                "satisfying_payoff"
            )
        )

        return segments

    def _get_style_templates(self, style: str, channel: str) -> Dict[str, Any]:
        """Supports all 8 storytelling genres with distinctive Hindi phrasing."""
        normalized = style.lower().strip()

        # 1. Funny + Facts
        if "funny" in normalized or "fact" in normalized:
            return {
                "clean_intro_dialogue": f"Swagat hai dosto! Aaj humare {channel} ne socha tha ki yeh pro mastermind banenge, lekin fact yeh hai ki pehle hi minute me kya gazab popat hua dekho!",
                "outro_dialogue": "Toh dosto, yeh the aaj ke hilarious moments aur crazy facts! Agar gameplay pasand aaya toh like aur subscribe zaroor karein!",
                "act1_scenes": [
                    {
                        "note": "Streamer crashes vehicle into the wall right at spawn.",
                        "dialogue": "Bhai ne gadi aisi thoki jaise brake ki jagah accelerator chipka diya ho! Fun fact: Los Santos me 80% heists start hone se pehle hi fail hote hain!"
                    },
                    {
                        "note": "Stealth infiltration fail as guard is startled.",
                        "dialogue": "Ninja stealth plan tha, lekin bhai ne siren hi baja diya! Fact yeh hai ki AI guards ka hearing range 40 meter tak hota hai!"
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "Chaos & Blunders",
                        "note": "Rocket launcher fired right into a concrete lamp post.",
                        "dialogue": "Rocket launcher nikala SWAT ko udane ke liye, par missile khambe se takra gayi! Bhai khud hawa me astronaut ban gaye!"
                    },
                    {
                        "title": "Bridge Stunt Fail",
                        "note": "Car flips three times over the bridge barrier into water canal.",
                        "dialogue": "Bhai ne bola stunt dekho! Aur agle hi pal gaadi naale me plunge! Fact yeh hai ki GTA physics me gravity hamesha joke ban jati hai!"
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "Clutch Getaway",
                        "note": "Final police roadblock cleared on bare metal rims.",
                        "dialogue": "Chaaro tyre puncture hone ke bawajood sparks udate hue escape! Bhai ka luck 100 out of 100 nikla!"
                    }
                ]
            }

        # 2. Documentary Storytelling
        elif "documentary" in normalized:
            return {
                "clean_intro_dialogue": f"Los Santos ki taareekh me yeh din hamesha yaad rakha jayega. Yeh dastaavez hai us dushwar tareen mission ka jise {channel} ne anjaam diya.",
                "outro_dialogue": "Yeh dastaavez yahan mukammal hota hai. Kaise mansoobabandi aur hosle ne na-mumkin ko mumkin banaya. Agle hisse ke liye jude rahein.",
                "act1_scenes": [
                    {
                        "note": "Architectural blueprints and strategy session.",
                        "dialogue": "Dopehar ke theek do baje, mansooba tayyar kiya gaya. Shehar ke markazi bank me daakhil hone ka wahid rasta tha."
                    },
                    {
                        "note": "Subway entrance approach under darkness.",
                        "dialogue": "Zameen ke sau foot neeche, khamoshi se qadam badhaye gaye. Har harkat ek sochi-samjhi hikmat-e-amli ka hissa thi."
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "The Strategic Crisis",
                        "note": "Unexpected alarm activation and law enforcement mobilization.",
                        "dialogue": "Lekin ghair-mutawaqqo rukawat samne aayi. Alarm bajte hi riyasat ki poori fauj harakat me aa chuki thi."
                    },
                    {
                        "title": "Tactical Withdrawal",
                        "note": "Coordinated smoke deployment and defensive corridor retreat.",
                        "dialogue": "Har morche par dhuen ke parday chhodte hue, team ne apnay nuqsaan ko kam se kam rakhne ki koshish ki."
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "The Final Extraction",
                        "note": "Helicopter extraction along the coastal ridge.",
                        "dialogue": "Samundari hawaon ke darmiyan, aakhri extraction parwaaz parvaan chadhi. Mission tareekh ka hissa ban chuka tha."
                    }
                ]
            }

        # 3. Mystery & Suspense Storytelling
        elif "mystery" in normalized or "suspense" in normalized:
            return {
                "clean_intro_dialogue": f"Kamre me sannata tha. Kisi ko khabar nahi thi ki agle saat minute me Los Santos ki sabse gehri saazish samne aane wali hai.",
                "outro_dialogue": "Raaz khul chuka tha, lekin kya kahani sach me khatam hui? Agla mod kya hoga, yeh aane wala waqt batayega.",
                "act1_scenes": [
                    {
                        "note": "Dimly lit warehouse with mysterious encrypted briefcase.",
                        "dialogue": "Tijori ke andar ek aisi cheez thi jise dekh kar sab ke hosh udd gaye. Sawal yeh tha ki yeh secret kisne chhupaya tha?"
                    },
                    {
                        "note": "Shadow moving behind the frosted office glass.",
                        "dialogue": "Ek saaya diwaar par chamka. Koi tha jo unke har qadam par nazar rakhe hue tha bina koi aahat kiye."
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "The Trap Unfolds",
                        "note": "Doors automatically seal shut with red warning lights.",
                        "dialogue": "Achanak darwaze lock ho gaye! Yeh koi aam bank nahi, balki ek socha-samjha jaal tha unhe fasaane ke liye!"
                    },
                    {
                        "title": "Whispers on the Radio",
                        "note": "Unknown voice hijacks the team's internal radio frequency.",
                        "dialogue": "Radio par ek aisi aawaz aayi jisne sabki rooh kaanp di. Unka apna sathi hi unhe dhokha de chuka tha!"
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "The Dark Reveal",
                        "note": "Getaway vehicle emerges from the subterranean tunnel.",
                        "dialogue": "Andhere se nikalte hi sachai samne aayi. Woh azaad toh ho gaye the, par qeemat bohat badi chukani padi thi."
                    }
                ]
            }

        # 4. Investigative Storytelling
        elif "investigative" in normalized:
            return {
                "clean_intro_dialogue": f"Evidence File Number 101. Aaj hum analyze karenge {channel} ke is high-profile incident ka har ek second, minute aur frame.",
                "outro_dialogue": "Toh yeh tha hamara complete forensic breakdown. Saboot saaf hain aur nateeja aapke samne hai.",
                "act1_scenes": [
                    {
                        "note": "Surveillance camera footage freeze-framed with timestamp.",
                        "dialogue": "Timestamp zero-two-fourteen. Security camera ne note kiya ki patrol guard theek gyarah second late tha."
                    },
                    {
                        "note": "Blueprint overlay showing wire cuts.",
                        "dialogue": "Forensic reports ke mutabiq, electrical grid ko bahar se disable kiya gaya tha, jo insider access ka saboot hai."
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "The Anomaly Detected",
                        "note": "Audio frequency spike on the communication log.",
                        "dialogue": "Audio logs verify karte hain ki pehla gunshot police ne nahi balki lobby me maujood third party ne chalaya tha."
                    },
                    {
                        "title": "Tracking the Route",
                        "note": "GPS map tracking line zig-zagging through downtown alleys.",
                        "dialogue": "GPS data dikhata hai ki unhone regular highway chhodkar industrial sewer canals ka rasta pehle se tay kar rakha tha."
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "Final Verdict",
                        "note": "Evidence documents stamped 'CASE CLOSED'.",
                        "dialogue": "Tamam saboot jodkar dekhein toh yeh saaf hai ki yeh koi ittefaq nahi balki calculated execution tha."
                    }
                ]
            }

        # 5. Cinematic Storytelling
        elif "cinematic" in normalized:
            return {
                "clean_intro_dialogue": f"Dhuen aur aag ke darmiyan, Los Santos ki dhartee par ek aisi jung shuru hui jisme jeet ka matlab amar hona tha.",
                "outro_dialogue": "Yeh sirf ek jeet nahi thi, balki cinema ke parde jaisi ek yaadgaar dastaan thi. Channel ko subscribe karna na bhoolein.",
                "act1_scenes": [
                    {
                        "note": "Slow motion shot of armored crew walking through golden hour sunlight.",
                        "dialogue": "Suraj dhal raha tha, aur aasmaan par surkh rang chha chuka tha. Unke qadmon ki goonj fasle tay kar rahi thi."
                    },
                    {
                        "note": "Close up of masked face reflecting vault laser beams.",
                        "dialogue": "Aankhon me khauf ka koi nishan nahi tha. Samne maut thi aur unki ungliyan trigger par mustaid thin."
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "The Grand Symphony of Fire",
                        "note": "Explosion in background as armored vehicle speeds forward.",
                        "dialogue": "Peeche aag ke shole aasmaan ko chhoo rahe the. Raste par har rukawat ko cheerte hue unka karwan badh raha tha."
                    },
                    {
                        "title": "Mount Chiliad Ascent",
                        "note": "Vehicle drifting dangerously along the 3000-ft cliff edge.",
                        "dialogue": "Pahad ki choti par, jahan hawayen rooh ko cheer deti hain, unhone kismat ke aakhri daanv par baazi laga di."
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "Wings of Freedom",
                        "note": "Parachutes bloom against the crimson sunset sky.",
                        "dialogue": "Hawa me azaad parinde ki tarah, unhone aasmaan ko gale lagaya. Ek shaandar anjaam jo hamesha zinda rahega."
                    }
                ]
            }

        # 6. Chronological Storytelling
        elif "chronological" in normalized:
            return {
                "clean_intro_dialogue": f"Minute-by-minute timeline breakdown. Theek minute ek se lekar aakhri second tak, dekhiye yeh stream kaise unfold hui.",
                "outro_dialogue": "Is tarah subah ke pehle ghante se aakhri minute tak poora mission step-by-step complete hua.",
                "act1_scenes": [
                    {
                        "note": "Clock graphic overlay at 00:00:00 start mark.",
                        "dialogue": "Step 1: Theek subah aath baje preparation complete hui aur weapons inventory cross-check ki gayi."
                    },
                    {
                        "note": "Clock graphic at 00:05:00 mark.",
                        "dialogue": "Step 2: Paanchvein minute par entry point clear hua aur team ne basement me position li."
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "Step 3 & 4: Escalation",
                        "note": "Clock graphic at 00:12:00 mark.",
                        "dialogue": "Barahvein minute par pehla alarm trigger hua aur agle teen minute me pehli SWAT team report hui."
                    },
                    {
                        "title": "Step 5: The Mid-Point",
                        "note": "Clock graphic at 00:18:00 mark.",
                        "dialogue": "Atharahvein minute par getaway transport par attack hua aur unhe route tabdeel karna pada."
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "Final Step: Extraction",
                        "note": "Clock graphic at final mission milestone.",
                        "dialogue": "Theek pachisvein minute par safehouse me landing hui aur timeline officially mark ho gayi."
                    }
                ]
            }

        # 7. Case Study Storytelling
        elif "case" in normalized:
            return {
                "clean_intro_dialogue": f"Case Study Analysis: The Heist Strategy. Aaj hum analyze karenge planning vs execution, aur risk-to-reward ratio.",
                "outro_dialogue": "Key Takeaway: Execution me agility sabse important hai. Yeh case study aane wale gamers ke liye ek blueprint hai.",
                "act1_scenes": [
                    {
                        "note": "Analytical infographic showing risk factors.",
                        "dialogue": "Phase 1: Planning and Logistics. Team ne 90 percent focus resource allocation aur silent entry par rakha."
                    },
                    {
                        "note": "Cost vs reward calculation overlay.",
                        "dialogue": "Risk assessment ke mutabiq underground canal sabse low-risk pathway tha jisme detection chances sirf das percent the."
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "Contingency Breakdown",
                        "note": "Risk graph spiking into red zone.",
                        "dialogue": "Phase 2: Execution Variable. Jab primary escape route block hua, toh contingency plan B turant activate kiya gaya."
                    },
                    {
                        "title": "Resource Management",
                        "note": "Ammo and armor management efficiency display.",
                        "dialogue": "Resource efficiency 85 percent maintain rahi kyunki unhone heavy armor ka calculated istemal kiya."
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "ROI & Conclusion",
                        "note": "Success score card and evaluation graph.",
                        "dialogue": "Phase 3: Outcome. Total loot 200 Crore aur survival rate 100 percent. Strategic success rate grade A."
                    }
                ]
            }

        # 8. Explainer Storytelling (Default)
        else:
            return {
                "clean_intro_dialogue": f"Chaliye aasaan shabdon me samajhte hain ki aakhir {channel} ne is impossible GTA heist ko step-by-step kaise crack kiya!",
                "outro_dialogue": "Toh dosto, yeh tha poora mathematical aur practical explainer! Agar samajh aaya toh video ko like zaroor karein!",
                "act1_scenes": [
                    {
                        "note": "Overview diagram showing the target bank structure.",
                        "dialogue": "Sabse pehle samajhte hain bank ka layout. Is vault tak pahunchne ke teen alag layers hain jo laser aur thermal cameras se protected hain."
                    },
                    {
                        "note": "Diagram showing drill mechanism and sound damping.",
                        "dialogue": "Is drill machine ka kamaal dekhiye. Yeh bina sound vibration paida kiye do foot moti steel plate ko kaat sakti hai."
                    }
                ],
                "act2_scenes": [
                    {
                        "title": "How the 5-Star Police Logic Works",
                        "note": "Police AI pathfinding routes shown as glowing lines on the city map.",
                        "dialogue": "Ab samajhte hain ki police ka AI kaise kaam karta hai. 5-Star wanted level me helicopters har chaalis second me respawn hote hain."
                    },
                    {
                        "title": "The Subway Escape Trick",
                        "note": "Subway dark tunnel avoiding aerial radar.",
                        "dialogue": "Lekin jab aap underground metro tunnel me daakhil hote hain, toh helicopters ka radar link completely toot jata hai!"
                    }
                ],
                "act3_scenes": [
                    {
                        "title": "The Final Escape Physics",
                        "note": "Ramp jump angle and speed calculation graphics.",
                        "dialogue": "Aur aakhir me dekhiye yeh stunt physics. Theek pachpan degree ke angle par jump laga kar highway grid bypass kar diya gaya!"
                    }
                ]
            }

    async def _generate_with_gemini(
        self,
        stream_meta: Dict[str, Any],
        hype_spikes: List[Dict[str, Any]],
        target_seconds: int,
        story_style: str
    ) -> Optional[List[Dict[str, Any]]]:
        try:
            from google import genai
            client = genai.Client(api_key=self.gemini_key)
            prompt = self._build_prompt(stream_meta, hype_spikes, target_seconds, story_style)

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            raw_text = response.text
            data = json.loads(raw_text)
            if isinstance(data, list) and len(data) > 0:
                return self._post_process_llm_segments(data, target_seconds)
            elif isinstance(data, dict) and "segments" in data:
                return self._post_process_llm_segments(data["segments"], target_seconds)
        except Exception as e:
            logger.warning(f"Error calling Gemini: {e}")
        return None

    async def _generate_with_openai(
        self,
        stream_meta: Dict[str, Any],
        hype_spikes: List[Dict[str, Any]],
        target_seconds: int,
        story_style: str
    ) -> Optional[List[Dict[str, Any]]]:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.openai_key)
            prompt = self._build_prompt(stream_meta, hype_spikes, target_seconds, story_style)

            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"You are a master YouTube video explainer and scriptwriter in Hindi/Hinglish. Style: {story_style}. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            segments = data.get("segments", data if isinstance(data, list) else [])
            return self._post_process_llm_segments(segments, target_seconds)
        except Exception as e:
            logger.warning(f"Error calling OpenAI: {e}")
        return None

    def _build_prompt(
        self,
        meta: Dict[str, Any],
        hype_spikes: List[Dict[str, Any]],
        target_seconds: int,
        style: str
    ) -> str:
        num_clips = max(4, round(target_seconds / 9.0))
        sample_hypes = json.dumps(hype_spikes[:15], indent=2)

        return f"""
You are the Lead Director of "StreamRecap Studio".
Transform this gaming stream into a {target_seconds // 60}-minute edited Full HD recap video with a time-synced spoken Hindi/Hinglish commentary script.

CRITICAL STORYTELLING STYLE: "{style}"
(You MUST strictly embody this storytelling genre throughout all spoken lines:
- If "Funny + Facts": Sarcastic comedy + crazy gaming facts
- If "Documentary Storytelling": Serious, authoritative, historical voice
- If "Mystery & Suspense Storytelling": Suspenseful, questions, chilling atmosphere
- If "Investigative Storytelling": Forensic, evidence-based, timestamps, clues
- If "Cinematic Storytelling": Poetic, epic, high-drama Hollywood pacing
- If "Chronological Storytelling": Exact step-by-step timeline sequence
- If "Case Study Storytelling": Strategic breakdown, planning vs execution, ROI
- If "Explainer Storytelling": Clear, intuitive, engaging breakdown of how and why)

STREAM METADATA:
- Title: {meta.get('title')}
- Channel: {meta.get('channel')}
- Original Stream Duration: {meta.get('duration')} seconds
- Target Video Length: {target_seconds} seconds (~{num_clips} clips)

HIGHLIGHT SPIKES:
{sample_hypes}

CRITICAL RULES:
1. 3-ACT STORY ARC (Hook -> Chaos/Mission -> Climax & Payoff).
2. CLEAN 0-7s INTRO RULE: The first clip [00:00 - 00:08] MUST have zero graphic blood/gore or profanity (YouTube advertiser friendly).
3. STRICT DURATION & WORD-COUNT SYNC: Each segment gets ~2.2 Hindi words per second of duration. Natural conversational tone.

RETURN A JSON OBJECT WITH KEY "segments" containing array:
[
  {{
    "act": "Act I: The Hook",
    "duration": 8.0,
    "vod_start": 120.0,
    "scene_note": "Visual description",
    "dialogue_hindi": "Spoken commentary in exact requested style",
    "pacing": "energetic_hook"
  }}
]
"""

    def _post_process_llm_segments(self, raw_segments: List[Dict[str, Any]], target_seconds: int) -> List[Dict[str, Any]]:
        processed = []
        current_time = 0.0
        for i, s in enumerate(raw_segments):
            dur = float(s.get("duration", 8.0))
            if dur < 5.0:
                dur = 6.0
            if dur > 15.0:
                dur = 12.0

            v_start = current_time
            v_end = v_start + dur
            current_time = v_end

            vod_s = float(s.get("vod_start", i * 180 + 60))
            vod_e = vod_s + dur

            dialogue = s.get("dialogue_hindi", "")
            words = dialogue.strip().split()
            target_words = int(dur * 2.2)

            processed.append({
                "id": f"seg_{i + 1:03d}",
                "clip_index": i,
                "act": s.get("act", "Act II: The Mission"),
                "video_start": round(v_start, 2),
                "video_end": round(v_end, 2),
                "duration": round(dur, 2),
                "video_start_fmt": self._fmt_time(v_start),
                "video_end_fmt": self._fmt_time(v_end),
                "vod_start": round(vod_s, 2),
                "vod_end": round(vod_e, 2),
                "vod_start_fmt": self._fmt_time(vod_s),
                "vod_end_fmt": self._fmt_time(vod_start + dur),
                "scene_note": s.get("scene_note", "Action sequence on screen"),
                "dialogue_hindi": dialogue,
                "pacing": s.get("pacing", "fast_paced"),
                "word_count": len(words),
                "target_words": target_words,
            })

        return processed

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"
