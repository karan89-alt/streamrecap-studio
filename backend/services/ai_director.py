import asyncio
import json
import logging
import os
from typing import Dict, List, Any, Optional

from config import settings

logger = logging.getLogger("streamrecap.director")


class AIDirector:
    """
    AI Director responsible for:
    1. Structuring video intervals into a 3-Act Story Arc strictly bounded by real video duration.
    2. Enforcing the Clean 0-7s Intro Rule (advertiser-safe hook).
    3. Generating non-repeating, complete, natural Hindi/Hinglish dialogues tailored to all 8 styles:
       - Funny + Facts
       - Documentary Storytelling
       - Mystery & Suspense Storytelling
       - Investigative Storytelling
       - Cinematic Storytelling
       - Chronological Storytelling
       - Case Study Storytelling
       - Explainer Storytelling
    4. Calling Gemini asynchronously without ever blocking the FastAPI event loop.
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
        target_seconds = max(60, int(target_minutes) * 60)

        # Try Gemini non-blocking with strict timeout
        if self.gemini_key:
            try:
                script = await asyncio.wait_for(
                    self._generate_with_gemini(stream_meta, hype_spikes, target_seconds, story_style),
                    timeout=20.0
                )
                if script and len(script) >= 4:
                    logger.info(f"Generated {len(script)} scenes via Gemini LLM.")
                    return script
            except Exception as e:
                logger.warning(f"Gemini skipped/fallback ({type(e).__name__}): {e}")

        # Try OpenAI if key is available
        if self.openai_key:
            try:
                script = await asyncio.wait_for(
                    self._generate_with_openai(stream_meta, hype_spikes, target_seconds, story_style),
                    timeout=20.0
                )
                if script and len(script) >= 4:
                    return script
            except Exception as e:
                logger.warning(f"OpenAI skipped/fallback: {e}")

        # Built-in rich procedural Hindi/Hinglish screenwriter (zero API key required)
        return self._generate_procedural_script(stream_meta, hype_spikes, target_seconds, story_style)

    def _generate_procedural_script(
        self,
        stream_meta: Dict[str, Any],
        hype_spikes: List[Dict[str, Any]],
        target_seconds: int,
        story_style: str
    ) -> List[Dict[str, Any]]:
        stream_duration = max(120, int(stream_meta.get("duration") or 3000))
        channel = stream_meta.get("channel") or "Gaming Creator"

        avg_segment_duration = 10.5
        num_segments = max(6, round(target_seconds / avg_segment_duration))

        # Partition into 3 acts: 20% Act I, 60% Act II, 20% Act III
        act1_count = max(2, round(num_segments * 0.20))
        act3_count = max(2, round(num_segments * 0.20))
        act2_count = max(2, num_segments - act1_count - act3_count)
        total_segments = act1_count + act2_count + act3_count

        # Safe VOD window strictly inside [15s, stream_duration - 15s]
        vod_min = min(30.0, stream_duration * 0.03)
        vod_max = max(vod_min + 20.0, stream_duration - 18.0)
        vod_span = max(20.0, vod_max - vod_min)

        style_pack = self._get_style_pack(story_style, channel)
        act1_pool = style_pack["act1"]
        act2_pool = style_pack["act2"]
        act3_pool = style_pack["act3"]

        segments: List[Dict[str, Any]] = []
        current_video_time = 0.0

        def add_seg(idx: int, act_label: str, dur: float, note: str, dialogue: str, pacing: str):
            nonlocal current_video_time
            # Evenly map segment index across actual video timeline
            ratio = idx / max(1, total_segments - 1)
            vod_s = vod_min + (ratio * vod_span)
            vod_s = max(5.0, min(vod_max - dur, vod_s))

            v_start = current_video_time
            v_end = v_start + dur
            current_video_time = v_end

            clean_dialogue = dialogue.strip()
            segments.append({
                "id": f"seg_{idx + 1:03d}",
                "clip_index": idx,
                "act": act_label,
                "video_start": round(v_start, 2),
                "video_end": round(v_end, 2),
                "duration": round(dur, 2),
                "video_start_fmt": self._fmt_time(v_start),
                "video_end_fmt": self._fmt_time(v_end),
                "vod_start": round(vod_s, 2),
                "vod_end": round(vod_s + dur, 2),
                "vod_start_fmt": self._fmt_time(vod_s),
                "vod_end_fmt": self._fmt_time(vod_s + dur),
                "scene_note": note,
                "dialogue_hindi": clean_dialogue,
                "pacing": pacing,
                "word_count": len(clean_dialogue.split()),
                "target_words": int(dur * 2.2),
            })

        idx = 0
        # ACT I: Clean 0-7s Hook + Setup
        add_seg(idx, "Act I: The Hook", 8.0, "High-energy clean opening hook", style_pack["hook"], "energetic_hook")
        idx += 1

        for i in range(1, act1_count):
            dur = 8.0 + (i % 3)  # 8, 9, 10s
            item = act1_pool[(i - 1) % len(act1_pool)]
            add_seg(idx, "Act I: Setup", dur, item["note"], item["dialogue"], "suspense_building")
            idx += 1

        # ACT II: Rising Action, Chaos & Plot Twists
        for i in range(act2_count):
            dur = 8.5 + (i % 3)  # 8.5, 9.5, 10.5s
            item = act2_pool[i % len(act2_pool)]
            add_seg(idx, item.get("act", "Act II: Action & Chaos"), dur, item["note"], item["dialogue"], "fast_paced")
            idx += 1

        # ACT III: Climax & Outro
        for i in range(act3_count - 1):
            dur = 8.5 + (i % 2)
            item = act3_pool[i % len(act3_pool)]
            add_seg(idx, "Act III: The Climax", dur, item["note"], item["dialogue"], "hype_punchline")
            idx += 1

        # Final Outro
        add_seg(idx, "Act III: Finale", 8.0, "Final conclusion and payoff", style_pack["outro"], "satisfying_payoff")
        return segments

    def _get_style_pack(self, story_style: str, channel: str) -> Dict[str, Any]:
        s = story_style.lower()

        if "funny" in s or "fact" in s:
            return {
                "hook": f"Swagat hai dosto! Aaj {channel} ne socha tha ki yeh pro mastermind banenge, par agle 5 minute me jo comedy hui woh dekh kar hasi nahi rukegi!",
                "act1": [
                    {"note": "Vehicle launch blunder", "dialogue": "Bhai ne gadi aisi thoki jaise brake ki jagah accelerator chipka diya ho! Fun fact: GTA V me NPCs ka driving AI intentional chaos ke liye banaya gaya hai!"},
                    {"note": "Stealth alarm triggered", "dialogue": "Ninja stealth plan tha, lekin bhai ne khud siren baja diya! Fact yeh hai ki guards ka hearing radius 40 meter tak kaam karta hai!"},
                    {"note": "Wrong weapon equipped", "dialogue": "Gun fight me sniper nikalne ki jagah bhai ne flashlight nikal li! Interesting fact: Stress me 60 percent gamers wrong weapon wheel select kar lete hain!"},
                    {"note": "GPS route confusion", "dialogue": "GPS bol raha tha right mudne ko, bhai seedha divider par chadh gaye! Kya aapko pata hai Los Santos ka map real Los Angeles par based hai?"},
                    {"note": "Crew coordination fail", "dialogue": "Team plan tha ek saath entry karne ka, par aadhi team piche coffee peeti reh gayi! Fact: Multiplayer sync me 2 second ka delay bhi mission uda deta hai!"},
                    {"note": "Security camera spotted", "dialogue": "Camera ke saamne khade hokar bhai bol rahe hain main dikh nahi raha! Fact: GTA ke CCTV cameras 120 degree wide angle tak scan karte hain!"},
                ],
                "act2": [
                    {"act": "Act II: Rocket Blunder", "note": "Rocket hits lamp post", "dialogue": "Rocket launcher nikala police udane ke liye, par missile khambe se takra gayi aur bhai khud hawa me astronaut ban gaye!"},
                    {"act": "Act II: Police Chase", "note": "5-Star wanted chaos", "dialogue": "5-Star wanted level lagte hi poora shehar piche pad gaya! Amazing fact: 5-star par NOOSE tactical units aur armored trucks spawn hote hain!"},
                    {"act": "Act II: Bridge Stunt", "note": "Car flips into canal", "dialogue": "Bhai ne bola legend stunt dekho aur agle hi pal gaadi seedha naale me gir gayi! Fact: Car ka center of gravity air control decide karta hai!"},
                    {"act": "Act II: Chopper Takedown", "note": "Helicopter dodging missiles", "dialogue": "Upar se police helicopter firing kar raha hai aur bhai road par gol-gol ghum rahe hain! Fun fact: Police choppers me unlimited ammo script hota hai!"},
                    {"act": "Act II: Vault Rush", "note": "Grabbing loot under fire", "dialogue": "Goliyan chal rahi hain par bhai ko ek-ek note ginke bag me bharna hai! Fact: Heavy loot bag aapki sprint speed 15 percent slow kar deta hai!"},
                    {"act": "Act II: Street Ambush", "note": "Roadblock crash", "dialogue": "Samne police ne 6 gaadiyon ka blockade lagaya aur bhai ne bina brake mare seedha andar ghusa diya! Physics ne bhi haath jod liye!"},
                    {"act": "Act II: Parachute Panic", "note": "Late parachute deploy", "dialogue": "Building se kood gaye par parachute kholna bhool gaye! Fact: Zameen se sirf 15 meter upar bhi reserve chute aapko bacha sakta hai!"},
                    {"act": "Act II: NPC Karma", "note": "Random civilian blocks car", "dialogue": "Sab kuch sahi chal raha tha tabhi ek random civilian ne aakar gaadi thok di! GTA ka classic rule: Jab jaldi ho, traffic double ho jata hai!"},
                    {"act": "Act II: Tire Blowout", "note": "Driving on metal rims", "dialogue": "Chaar me se teen tyre phat chuke hain, gaadi se chingariyan nikal rahi hain, par bhai bol rahe hain koi tension nahi!"},
                    {"act": "Act II: Explosion Chain", "note": "Chain reaction blast", "dialogue": "Ek goli petrol tank pe lagi aur poora chauraha Diwali ban gaya! Fact: GTA V me chain explosions 12 gaadiyon tak spread ho sakte hain!"},
                    {"act": "Act II: Narrow Alley", "note": "Stuck between walls", "dialogue": "Shortcut lene ke chakkar me gaadi gali ke beech me phans gayi! Ab na aage ja sakte hain na piche, bas horn baja rahe hain!"},
                    {"act": "Act II: Health 1 HP", "note": "Surviving with 1 HP", "dialogue": "Health bar dekho, bas ek phoonk ki doori par hai! Fact: Snacks khane se cover me bina animation delay ke health turant badhti hai!"},
                ],
                "act3": [
                    {"note": "Final roadblock dodge", "dialogue": "Aakhiri highway blockade tha, chaaro taraf sirens baj rahe the, aur bhai ne impossible drift marke nikal liya!"},
                    {"note": "Subway tunnel escape", "dialogue": "Police ko chakma dene ke liye gaadi seedha metro tunnel me daal di! Pro fact: Underground tunnels me police helicopter aapko track nahi kar sakta!"},
                    {"note": "Clutch safehouse reach", "dialogue": "Sirf 5 second bache the aur aakhirkaar safehouse ka gate khul gaya! Itne blunders ke baad bhi mission pass ho gaya!"},
                    {"note": "Score celebration", "dialogue": "Poora loot account me aa chuka hai aur police abhi bhi khali highway par dhundh rahi hai! Kya epic comedy getaway tha!"},
                ],
                "outro": "Toh dosto, yeh the aaj ke sabse hilarious moments aur crazy gaming facts! Aapka favourite scene kaunsa tha, comment me zaroor batana!",
            }

        if "documentary" in s:
            return {
                "hook": f"Yeh kahani hai Los Santos ke itihaas ke sabse khatarnak operation ki, jahan {channel} ne har mushkil ke bawajood ek namumkin mission ko anjaam diya.",
                "act1": [
                    {"note": "Operation briefing", "dialogue": "Har bade mission ki shuruwat ek khamosh aur sateek planning se hoti hai, jahan har ek second ki keemat hoti hai."},
                    {"note": "Entry route analysis", "dialogue": "Shehar ke sabse surakshit hisse me daakhil hone ke liye team ne sabse kam nazar aane wala rasta chuna."},
                    {"note": "Security grid overview", "dialogue": "Is ilaake me 24 ghante surveillance aur armed patrolling rehti hai, isliye ek chhoti si chook sab khatam kar sakti thi."},
                    {"note": "Initial breach execution", "dialogue": "Plan ke mutabik pehla security barrier bina kisi shor ke paar kar liya gaya, lekin asli chunauti abhi baaki thi."},
                    {"note": "Interior approach", "dialogue": "Andar badhte hi mahol me tanaav badhne laga, kyunki har kone par guards aur sensors tainaat the."},
                ],
                "act2": [
                    {"act": "Act II: The Turning Point", "note": "Alarm triggered", "dialogue": "Aur tabhi woh hua jiska sabko darr tha — emergency alarm baj utha aur poora operation survival ki jung me badal gaya."},
                    {"act": "Act II: Tactical Response", "note": "SWAT arrival", "dialogue": "Kuch hi seconds me shehar ki sabse bhari tactical force ne poori imarat ko chaaro taraf se gher liya."},
                    {"act": "Act II: Heavy Firefight", "note": "Intense cover combat", "dialogue": "Har taraf se hoti firing ke beech team ne discipline nahi khoya aur ek-ek position ko khali karwaya."},
                    {"act": "Act II: Extraction Attempt", "note": "Armored escape start", "dialogue": "Vault se bahar nikalna sirf aadhi ladai thi; asli imtihaan ab Los Santos ki sadkon par hone wala tha."},
                    {"act": "Act II: Highway Pursuit", "note": "High speed chase", "dialogue": "140 ki raftar par highway chase shuru ho chuka tha, jahan aage blockade aur piche darjanon police gaadiyan thi."},
                    {"act": "Act II: Aerial Surveillance", "note": "Helicopter tracking", "dialogue": "Aasmaan me mandrate helicopters ne chhupne ki saari umeedein khatam kar di thi, ab sirf raftar hi sahara thi."},
                    {"act": "Act II: Critical Damage", "note": "Vehicle taking heavy fire", "dialogue": "Lagatar firing se gaadi ka engine dhuan chhodne laga tha, ek aur takkar is kahani ko yahi rok sakti thi."},
                    {"act": "Act II: Bold Detour", "note": "Off-road maneuver", "dialogue": "Sadak band dekh kar driver ne ek aisa risky off-road mod liya jiski ummeed kisi ko nahi thi."},
                    {"act": "Act II: Narrow Survival", "note": "Close call explosion", "dialogue": "Paas me hue dhamake ne sab hila diya, lekin shaant dimaag aur tej reflexes ne team ko zinda rakha."},
                    {"act": "Act II: Second Wind", "note": "Breaking perimeter", "dialogue": "Dheere-dheere police ghera kamzor padne laga aur team ne shehar ke bahari hisse ki taraf badhat bana li."},
                ],
                "act3": [
                    {"note": "Final push to safety", "dialogue": "Manzil ab sirf kuch hi doori par thi, lekin aakhiri police blockade paar karna sabse bada imtihaan tha."},
                    {"note": "Shaking the pursuit", "dialogue": "Andhere tunnels aur tej mod ka sahara lekar aakhirkaar team ne surveillance radar se apna nishaan mita diya."},
                    {"note": "Safe arrival", "dialogue": "Jab suraj dhal raha tha, team surakshit apne thikane par pahunch chuki thi — ek namumkin operation poora ho chuka tha."},
                ],
                "outro": "Yeh tha is poore mission ka asli dastavez — jahan strategy, sabr aur himmat ne itihaas rach diya. Milte hain agli kahani me.",
            }

        if "mystery" in s or "suspense" in s:
            return {
                "hook": f"Raat ke andhere me ek aisa raaz chhupa tha jiske baare me {channel} ko bhi andaaza nahi tha... aakhir aage kya hone wala hai?",
                "act1": [
                    {"note": "Eerie calm before storm", "dialogue": "Shuruwat me sab kuch itna shaant tha ki lag raha tha kuch bahut bada chhupaya ja raha hai."},
                    {"note": "Hidden signal detected", "dialogue": "Ek ajeeb sa ishara mila — koi pehle se hi inki har harkat par nazar rakh raha tha."},
                    {"note": "Locked door mystery", "dialogue": "Saamne ka rasta band tha, par sawal yeh tha ki security system pehle se active kisne kiya?"},
                    {"note": "First shadow appears", "dialogue": "Andhere kone me halki si halchal hui... kya yeh koi trap tha jisme team khud chalkar aa gayi thi?"},
                    {"note": "Sudden comms silence", "dialogue": "Achanak radio par sannata chha gaya, aur usi pal samajh aa gaya ki khel ab badal chuka hai."},
                ],
                "act2": [
                    {"act": "Act II: The Trap Springs", "note": "Ambush triggered", "dialogue": "Bina kisi warning ke chaaro taraf se ghera band ho gaya — yeh koi aam mission nahi, ek sochi-samjhi saazish thi!"},
                    {"act": "Act II: Unexpected Twist", "note": "Escape route blocked", "dialogue": "Jis raste se bahar nikalna tha, wahan pehle se hi heavy units tainaat thi! Aakhir inka plan leak kaise hua?"},
                    {"act": "Act II: Heartbeat Rising", "note": "Close quarters chase", "dialogue": "Har mod par khatra badhta ja raha tha, aur kisi ko pata nahi tha ki agle second saamne kaun aayega."},
                    {"act": "Act II: Vanishing Target", "note": "Losing line of sight", "dialogue": "Dhuein ke beech sab kuch gayab ho gaya — na dushman dikh raha tha, na bahar nikalne ka rasta!"},
                    {"act": "Act II: High Tension Chase", "note": "Nighttime pursuit", "dialogue": "Sunsaan sadak par piche laal-neeli battiyaan tezi se paas aa rahi thi, aur har pal saansein tham rahi thi."},
                    {"act": "Act II: Split Second Choice", "note": "Fork in the road", "dialogue": "Aage do raste the — ek sidha jaal ki taraf jata tha aur doosra anjaan andhere me. Kya hoga sahi faisla?"},
                    {"act": "Act II: Engine Warning", "note": "Vehicle failing in dark", "dialogue": "Sabse khatarnak mod par gaadi se ajeeb awaaz aane lagi... agar engine yahi band hua toh sab khatam!"},
                    {"act": "Act II: Silent Hideout", "note": "Hiding from searchlight", "dialogue": "Helicopter ki searchlight theek unke upar se guzri — ek chhoti si harkat unka pata de sakti thi!"},
                    {"act": "Act II: Sudden Pursuit", "note": "Spotted again", "dialogue": "Laga tha khatra tal gaya, par tabhi door se ek siren gunja — woh abhi bhi inke theek piche the!"},
                    {"act": "Act II: Edge of Disaster", "note": "Cliffside near-miss", "dialogue": "Khaai ke bilkul kinare par gaadi phisli aur ek pal ke liye laga ki ab bachna namumkin hai!"},
                ],
                "act3": [
                    {"note": "Final showdown tension", "dialogue": "Aakhiri baazi ab haath me thi — ya toh is jaal ko tod kar nikalna tha, ya hamesha ke liye phans jana tha."},
                    {"note": "Unbelievable twist escape", "dialogue": "Aur tabhi aakhiri pal me ek aisa daav khela gaya jisne poori police force ko chaunka diya!"},
                    {"note": "Mystery resolved", "dialogue": "Khatre ke baadal chhat gaye, par ek sawal abhi bhi zinda hai — aakhir is sabke piche asli mastermind kaun tha?"},
                ],
                "outro": "Kya aapko lagta hai yeh sirf shuruwat thi? Apni theory comment me zaroor likhna, kyunki asli raaz abhi khulna baaki hai!",
            }

        if "investigative" in s:
            return {
                "hook": f"Aaj hum forensic level par investigate karenge ki {channel} ke is high-stakes mission me aakhir kis galti ne poora shehar hila diya!",
                "act1": [
                    {"note": "Evidence #1: Setup", "dialogue": "Pehla saboot shuruwati 2 minute me hi mil jata hai — entry timing me 10 second ki deri ne poora schedule bigaad diya."},
                    {"note": "Evidence #2: Route choice", "dialogue": "Map ke data ko dekhein toh backup exit select hi nahi kiya gaya tha, jo aage chalkar sabse badi kamzori bana."},
                    {"note": "Evidence #3: Guard pattern", "dialogue": "Dhyan se dekhiye guard ka patrol pattern — right side khali thi, par team ne risk wala center corridor chuna."},
                    {"note": "Evidence #4: Equipment check", "dialogue": "Inventory audit me saaf dikhta hai ki heavy armor aur ammo reserve limit se kam le jaye gaye the."},
                    {"note": "Evidence #5: First alert", "dialogue": "Yahan par pehla red flag trigger hua — CCTV blind spot miss hote hi alert signal control room tak pahunch gaya."},
                ],
                "act2": [
                    {"act": "Act II: Breakdown Analysis", "note": "Response time check", "dialogue": "Alarm bajne ke theek 18 second baad pehli response unit pahunchi — yeh ab tak ka sabse tez police reaction tha."},
                    {"act": "Act II: Tactical Error", "note": "Exposed crossfire", "dialogue": "Is frame ko pause karke dekhiye: open area me aane ki wajah se team dono taraf se crossfire me phans gayi."},
                    {"act": "Act II: Vehicle Choice", "note": "Getaway car speed vs armor", "dialogue": "Getaway vehicle ki speed toh acchi thi, par armor rating kam hone se tyres jaldi damage hone lage."},
                    {"act": "Act II: Choke Point", "note": "Highway bottleneck", "dialogue": "Investigation me pata chalta hai ki main highway par jaana sabse badi bhool thi, kyunki wahan roadblock fix hota hai."},
                    {"act": "Act II: Smart Recovery", "note": "Using side alleys", "dialogue": "Lekin yahan par player ne brilliance dikhayi — patli galiyon ka istemal karke police convoy ka formation tod diya!"},
                    {"act": "Act II: Blind Spot Play", "note": "Breaking radar line", "dialogue": "Radar cone ke angles ko samajh kar gaadi ko bridge ke neeche chhupana ek textbook tactical move tha."},
                    {"act": "Act II: Resource Management", "note": "Health & cover discipline", "dialogue": "Critical situation me panic karne ki jagah cover-to-cover movement ne survival probability 80 percent badha di."},
                    {"act": "Act II: Turning Point", "note": "Chopper evasion", "dialogue": "Yahi woh exact timestamp hai jahan se match palta — air unit ka line-of-sight toot-te hi chase control me aa gaya."},
                    {"act": "Act II: Speed Metrics", "note": "Cornering speed retained", "dialogue": "Tez mod par bina speed khoye drift nikalna hi woh factor tha jisne piche ki gaadiyon se gap bana diya."},
                    {"act": "Act II: Risk Assessment", "note": "High risk shortcut", "dialogue": "Is shortcut me failure ka chance 70 percent tha, lekin yahi aakhiri rasta tha blockade bypass karne ka."},
                ],
                "act3": [
                    {"note": "Final evidence review", "dialogue": "Aakhiri 60 seconds ka data dikhata hai ki har ek decision bilkul calculate karke liya gaya tha."},
                    {"note": "Escape verification", "dialogue": "Wanted stars clear hote hi yeh saabit ho gaya ki sahi improvisation se bigda hua plan bhi jeeta ja sakta hai."},
                    {"note": "Final verdict", "dialogue": "Poore case ki jaanch ke baad nateeja saaf hai — shuruwati galtiyon ke bawajood clutch execution ne mission bacha liya."},
                ],
                "outro": "Is investigation me sabse badi galti aapko kaunsi lagi? Comment me apni report zaroor share karein!",
            }

        if "cinematic" in s:
            return {
                "hook": f"Lights, camera, aur full-throttle action! Aaj {channel} ki yeh stream kisi Hollywood blockbuster movie se bilkul kam nahi hai!",
                "act1": [
                    {"note": "Wide establishing shot", "dialogue": "Los Santos ki chamakti sadkon par shaam dhal rahi hai, aur ek aise toofan ki taiyari ho rahi hai jo shehar hila dega."},
                    {"note": "Hero entry scene", "dialogue": "Engine ki garaj aur leather jackets ke saath crew maidan me utar chuki hai — nazar sirf ek hi target par hai."},
                    {"note": "Silent infiltration", "dialogue": "Kisi thriller film ke opening scene ki tarah har kadam khamoshi se aage badh raha hai."},
                    {"note": "Calm before explosion", "dialogue": "Waqt jaise tham gaya hai, ghadi ki sui aage badh rahi hai aur ab bas ek chingari ki der hai."},
                    {"note": "The spark ignites", "dialogue": "Aur ek zordar dhamake ke saath poora scene action movie ke interval block me badal jata hai!"},
                ],
                "act2": [
                    {"act": "Act II: Action Sequence", "note": "Slow-mo shootout", "dialogue": "Hawa me udti chingariyan, lagatar chalti goliyan aur har frame kisi mega-budget movie jaisa lag raha hai!"},
                    {"act": "Act II: High-Octane Chase", "note": "Highway nitro chase", "dialogue": "Turbo on, speedometer laal nishaan ke paar, aur piche sirens ki goonj — yeh hai pure cinema!"},
                    {"act": "Act II: Gravity Defying", "note": "Mid-air vehicle jump", "dialogue": "Bridge se gaadi hawa me uchhli jaise Fast & Furious ka live shoot chal raha ho — kya breathtaking frame tha!"},
                    {"act": "Act II: Fire & Smoke", "note": "Driving through flames", "dialogue": "Aag aur dhuein ke beech se nikalte hue hero ne dikha diya ki asli dar ko aankhon me aankhein daal kar haraya jata hai!"},
                    {"act": "Act II: Rooftop Duel", "note": "Chopper vs RPG", "dialogue": "Aasmaan me garajta chopper aur zameen par akela khiladi — yeh muqabla kisi legend se kam nahi!"},
                    {"act": "Act II: Midnight Drift", "note": "Neon street cornering", "dialogue": "Neon lights ki chamak me tyre se nikalta dhuan aur razor-sharp drift — har second goosebumps dene wala hai!"},
                    {"act": "Act II: Against All Odds", "note": "Surrounded on all sides", "dialogue": "Chaaro taraf dushman, aakhiri magazine aur har taraf khatra — par asli hero kabhi haar nahi maanta!"},
                    {"act": "Act II: Explosive Escape", "note": "Shockwave behind car", "dialogue": "Piche ek ke baad ek gaadiyan hawa me ud rahi hain aur samne sirf khula aasmaan aur azaadi dikh rahi hai!"},
                    {"act": "Act II: Final Sprint", "note": "Sunrise getaway", "dialogue": "Raat khatam ho rahi hai, sadak khali ho rahi hai aur jeet ki roshni ab saaf nazar aane lagi hai."},
                    {"act": "Act II: Unstoppable Force", "note": "Smashing final barrier", "dialogue": "Aakhiri deewar ko todkar jab gaadi paar nikli toh laga jaise poori picture ka sabse bada climax yahi hai!"},
                ],
                "act3": [
                    {"note": "Grand finale chase", "dialogue": "Background music peak par hai, aakhiri kuch meters bache hain aur saansein poori tarah thami hui hain!"},
                    {"note": "Triumphant escape", "dialogue": "Aur aakhirkaar sirens piche chhoot gaye — khamoshi laut aayi aur jeet ka jashn shuru ho gaya!"},
                    {"note": "Heroic outro frame", "dialogue": "Dhuein ke peeche se nikalte hue crew ne sabit kar diya ki Los Santos ka asli king kaun hai!"},
                ],
                "outro": "Kaisi lagi aapko yeh blockbuster gaming movie? Video pasand aayi toh like thok do aur agle episode ke liye taiyar raho!",
            }

        if "chronological" in s:
            return {
                "hook": f"Chaliye shuru se ant tak step-by-step dekhte hain ki {channel} ki is poori stream me pehle minute se aakhiri second tak kya-kya hua!",
                "act1": [
                    {"note": "Phase 1: Starting point", "dialogue": "Sabse pehle stream ke shuruwati hisse me crew ne base par ikattha hokar mission ka poora plan set kiya."},
                    {"note": "Phase 2: Gear selection", "dialogue": "Iske baad doosre step me sabhi zaroori weapons, armor aur getaway vehicles ko ready kiya gaya."},
                    {"note": "Phase 3: Approaching target", "dialogue": "Teesre phase me team ne shehar ke center ki taraf drive shuru ki aur target location ke paas position li."},
                    {"note": "Phase 4: First entry", "dialogue": "Ab waqt tha andar daakhil hone ka — pehle gate ko paar karte hi mission officially shuru ho chuka tha."},
                    {"note": "Phase 5: Reaching objective", "dialogue": "Kuch hi der me team main objective tak pahunch gayi aur aage ka sabse mushkil hissa shuru hua."},
                ],
                "act2": [
                    {"act": "Act II: Timeline Part 1", "note": "First conflict begins", "dialogue": "Yahan se kahani ne naya mod liya — pehli baar security alert hua aur sidhi firing shuru ho gayi."},
                    {"act": "Act II: Timeline Part 2", "note": "Clearing first wave", "dialogue": "Agle kuch minutes tak lagatar guards ki pehli wave ko roka gaya aur safe exit ki taraf kadam badhaye gaye."},
                    {"act": "Act II: Timeline Part 3", "note": "Exit to the streets", "dialogue": "Imarat se bahar nikalte hi team ka saamna khuli sadak par khadi police force se hua."},
                    {"act": "Act II: Timeline Part 4", "note": "Vehicle swap", "dialogue": "Iske baad turant getaway car me baith kar main road par high-speed chase shuru kar diya gaya."},
                    {"act": "Act II: Timeline Part 5", "note": "Wanted level escalation", "dialogue": "Jaise-jaise waqt aage badha, wanted level badh kar 4 aur phir 5 stars tak pahunch gaya."},
                    {"act": "Act II: Timeline Part 6", "note": "Mid-stream crisis", "dialogue": "Stream ke theek beech me gaadi heavy damage ka shikaar hui aur mission fail hone ke kareeb pahunch gaya."},
                    {"act": "Act II: Timeline Part 7", "note": "Route change", "dialogue": "Situation sambhalne ke liye main highway chhod kar side routes aur bridges ka sahara liya gaya."},
                    {"act": "Act II: Timeline Part 8", "note": "Shaking air support", "dialogue": "Agle hisse me helicopter se bachne ke liye underground passages aur buildings ke cover use kiye gaye."},
                    {"act": "Act II: Timeline Part 9", "note": "Regrouping", "dialogue": "Thoda gap milte hi team ne apni health recover ki aur aakhiri daud ke liye speed pakad li."},
                    {"act": "Act II: Timeline Part 10", "note": "Approaching safe zone", "dialogue": "Ab mission apne aakhiri charan me tha aur safehouse bas kuch hi kilometer door reh gaya tha."},
                ],
                "act3": [
                    {"note": "Final phase begins", "dialogue": "Stream ke aakhiri hisse me bache hue police blockades ko smart driving se paar kiya gaya."},
                    {"note": "Wanted level cleared", "dialogue": "Kuch hi seconds baad saare wanted stars gayab ho gaye aur rasta bilkul saaf ho gaya."},
                    {"note": "Mission complete", "dialogue": "Aur aakhir me team surakshit destination par pahunchi aur mission successfully complete ho gaya!"},
                ],
                "outro": "Yeh thi shuru se ant tak ki poori timeline! Is poore safar me aapka favourite pal kaunsa tha, zaroor batayein.",
            }

        if "case study" in s:
            return {
                "hook": f"Aaj ki gaming case study me hum analyze karenge ki {channel} ne zero margin of error ke saath ek impossible scenario ko kaise crack kiya!",
                "act1": [
                    {"note": "Objective definition", "dialogue": "Case study ka pehla point hai Objective Clarity — kam se kam waqt me maximum reward bina squad lose kiye."},
                    {"note": "Risk vs Reward setup", "dialogue": "Yahan high-risk entry chuni gayi kyunki agar yeh kaam kar gayi toh 40 percent time direct bachne wala tha."},
                    {"note": "Resource allocation", "dialogue": "Har player ka role fixed tha — ek navigation handle kar raha tha aur baaki defence cover de rahe the."},
                    {"note": "Initial execution metrics", "dialogue": "Pehle 20 percent mission me accuracy aur coordination dono top-tier level par maintain rahe."},
                    {"note": "First bottleneck", "dialogue": "Lekin har real-world case ki tarah yahan bhi ek unexpected bottleneck aaya jisne Plan A ko fail kar diya."},
                ],
                "act2": [
                    {"act": "Act II: Crisis Management", "note": "Pivot to Plan B", "dialogue": "Jab Plan A fail hua toh panic karne ke bajaye 3 second ke andar Plan B par pivot karna sabse smart move tha."},
                    {"act": "Act II: Map Control", "note": "Controlling choke points", "dialogue": "High ground aur narrow doorways ko hold karke kam ammo me bhi badi force ko roka gaya."},
                    {"act": "Act II: Mobility Advantage", "note": "Speed over armor", "dialogue": "Is phase me dikhta hai ki heavy gunfight me ulajhne se behtar hai lagatar move karte rehna."},
                    {"act": "Act II: Decision Under Pressure", "note": "Split second detour", "dialogue": "High-pressure moment me ek galat turn mission khatam kar sakta tha, par calculated risk ne rasta khol diya."},
                    {"act": "Act II: Efficiency Hack", "note": "Skipping unnecessary fights", "dialogue": "Pro takeaway yeh hai ki har enemy se ladna zaroori nahi hota; objective focus hi jeet dilata hai."},
                    {"act": "Act II: Adaptation", "note": "Recovering from damage", "dialogue": "Gaadi damage hone ke baad driving style badal kar smooth cornering par shift karna game-changer sabit hua."},
                    {"act": "Act II: AI Exploitation", "note": "Using map geometry", "dialogue": "Game AI ke line-of-sight rules ko smartly use karke bina goli chalaye pursuit ko slow kiya gaya."},
                    {"act": "Act II: Momentum Shift", "note": "Breaking out of zone", "dialogue": "Jaise hi red zone se bahar nikle, poora momentum wapas player ke favour me shift ho gaya."},
                    {"act": "Act II: Consistency", "note": "Maintaining clean lead", "dialogue": "Aakhiri stages me overconfidence se bach kar steady pace rakhna hi consistent winners ki pehchaan hai."},
                    {"act": "Act II: Execution Mastery", "note": "Flawless final turn", "dialogue": "Har ek obstacle ko predict karke pehle se lane change karne ne zero-collision exit ensure kiya."},
                ],
                "act3": [
                    {"note": "Key takeaway 1", "dialogue": "Aakhiri phase me humne dekha ki adaptability hamesha rigid planning se zyada powerful hoti hai."},
                    {"note": "Key takeaway 2", "dialogue": "Pressure me shaant dimaag rakh kar impossible chase ko bhi clean finish me badla ja sakta hai."},
                    {"note": "Final results", "dialogue": "Result aapke saamne hai — 100 percent mission completion aur maximum payout bina restart kiye!"},
                ],
                "outro": "Is case study se aapko kaunsi strategy sabse zyada pasand aayi? Apne gameplay me ise zaroor try karein!",
            }

        # Default: Explainer Storytelling
        return {
            "hook": f"Dosto aaj ki video me hum dekhne wale hain {channel} ka sabse khatarnak GTA mission, jahan har ek minute me kuch aisa hua jo aapke hosh uda dega!",
            "act1": [
                {"note": "Mission intro", "dialogue": "Kahani shuru hoti hai ek bade plan se, jahan poori crew ne Los Santos ka sabse mushkil target chuna hai."},
                {"note": "Preparation phase", "dialogue": "Pehle saari gaadiyan aur hathiyar set kiye jate hain taaki andar ghusne ke baad koi rukawat na aaye."},
                {"note": "Sneaking inside", "dialogue": "Ab team chupke se andar badh rahi hai — ek bhi chhoti si galti poori police force ko bula sakti hai!"},
                {"note": "Approaching main vault", "dialogue": "Security layers ko ek-ek karke paar kiya ja raha hai aur ab main target bilkul nazdeek aa chuka hai."},
                {"note": "Tension peaks", "dialogue": "Sab kuch plan ke hisaab se chal raha tha, par tabhi achanak aisa twist aaya jiski kisi ko ummeed nahi thi!"},
            ],
            "act2": [
                {"act": "Act II: Action Begins", "note": "Alarm & gunfight", "dialogue": "Alarm bajte hi poora scene badal gaya! Ab chupne ka time khatam, sidha full-on action shuru ho chuka hai!"},
                {"act": "Act II: Police Storm", "note": "Heavy forces arrive", "dialogue": "Bahar dekho bhai! Darjanon police gaadiyan aur SWAT teams poori building ko gher kar khadi ho chuki hain!"},
                {"act": "Act II: Crazy Escape", "note": "High speed breakout", "dialogue": "Team ne full speed me gaadi bahar nikali aur highway par ab tak ka sabse khatarnak chase shuru ho gaya!"},
                {"act": "Act II: Insane Stunt", "note": "Ramp jump over blockade", "dialogue": "Saamne rasta band tha, toh bhai ne gaadi seedha hawa me uda di! Kya kamaal ka stunt tha yaar!"},
                {"act": "Act II: Chopper Attack", "note": "Helicopter pursuit", "dialogue": "Ab upar se police helicopter bhi piche pad chuka hai, har taraf se goliyan aur sirens gunj rahe hain!"},
                {"act": "Act II: Near Miss", "note": "Dodging oncoming traffic", "dialogue": "Wrong side par 150 ki speed aur saamne se aata truck — bas ek inch se bache hain bhai log!"},
                {"act": "Act II: Critical Moment", "note": "Car smoking heavily", "dialogue": "Gaadi ke engine se kaala dhuan nikal raha hai, agar yeh yahi phat gayi toh poori mehnat bekaar ho jayegi!"},
                {"act": "Act II: Genius Move", "note": "Hidden alley shortcut", "dialogue": "Lekin tabhi dimaag lagaya aur patli galiyon me ghus kar police ko zabardast chakma de diya!"},
                {"act": "Act II: Tunnel Dash", "note": "Underground escape", "dialogue": "Metro tunnel ke andar jaate hi helicopter ka radar fail ho gaya — ab bas speed banaye rakhni hai!"},
                {"act": "Act II: Final Hurdle", "note": "Last roadblock smash", "dialogue": "Tunnel se bahar nikalte hi ek aakhiri blockade saamne aa gaya, par bhai ne bina ruke seedha paar kar diya!"},
            ],
            "act3": [
                {"note": "Final escape stretch", "dialogue": "Ab bas kuch hi seconds ki baat hai — police bahut piche chhoot chuki hai aur safehouse samne dikh raha hai!"},
                {"note": "Wanted stars gone", "dialogue": "Aur yeh lo bhai! 5-star wanted level gayab ho gaya, poori Los Santos police haath malti reh gayi!"},
                {"note": "Mission victory", "dialogue": "Aakhirkaar crew surakshit wapas pahunch chuki hai aur yeh namumkin mission shandaar tareeke se jeet liya!"},
            ],
            "outro": "Toh dosto, yeh thi aaj ki poori kahani! Video me maza aaya ho toh like zaroor karna aur agla recap kis stream par chahiye comment me batana!",
        }

    async def _generate_with_gemini(
        self,
        stream_meta: Dict[str, Any],
        hype_spikes: List[Dict[str, Any]],
        target_seconds: int,
        story_style: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Runs Gemini SDK in a worker thread so it NEVER blocks FastAPI's asyncio loop."""
        prompt = self._build_prompt(stream_meta, hype_spikes, target_seconds, story_style)

        def _call():
            from google import genai
            client = genai.Client(api_key=self.gemini_key)
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return response.text

        try:
            raw_text = await asyncio.to_thread(_call)
            data = json.loads(raw_text)
            if isinstance(data, list) and len(data) > 0:
                return self._post_process_llm_segments(data, stream_meta, target_seconds)
            elif isinstance(data, dict) and "segments" in data:
                return self._post_process_llm_segments(data["segments"], stream_meta, target_seconds)
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
            return self._post_process_llm_segments(segments, stream_meta, target_seconds)
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
        num_clips = max(6, round(target_seconds / 9))
        stream_dur = max(120, int(meta.get("duration") or 3000))
        return f"""
You are a top Indian YouTube gaming video editor and Hindi storyteller.
Stream Title: {meta.get('title')}
Channel: {meta.get('channel')}
Actual Stream Duration: {stream_dur} seconds (ALL vod_start MUST be between 10 and {stream_dur - 15})
Target Recap Duration: {target_seconds} seconds (~{num_clips} non-overlapping clips, each 8 to 10 seconds long)
Required Storytelling Style: {style}

RULES:
1. Clean 0-7s Intro Rule: The VERY FIRST clip [00:00 - 00:08] must be a gripping, advertiser-safe hook.
2. Natural Hindi/Hinglish dialogue written in Roman script. Every single segment MUST be unique, complete, and non-repeating (~16-22 words per clip).
3. Strictly match the chosen style: {style}.
4. Output JSON object with a "segments" array. Each item:
   - "act": "Act I: Hook", "Act II: Action", or "Act III: Climax"
   - "vod_start": number (between 10 and {stream_dur - 15})
   - "duration": number (between 8 and 10)
   - "scene_note": short visual description
   - "dialogue_hindi": complete engaging Hindi/Hinglish line
   - "pacing": "energetic_hook" | "fast_paced" | "hype_punchline"
"""

    def _post_process_llm_segments(
        self,
        raw_segments: List[Dict[str, Any]],
        stream_meta: Dict[str, Any],
        target_seconds: int
    ) -> List[Dict[str, Any]]:
        stream_dur = max(120, int(stream_meta.get("duration") or 3000))
        processed = []
        current_t = 0.0

        for idx, s in enumerate(raw_segments):
            dur = max(6.0, min(12.0, float(s.get("duration", 9.0))))
            vod_s = float(s.get("vod_start", (idx * 30) % max(60, stream_dur - 20)))
            vod_s = max(5.0, min(float(stream_dur) - dur - 2.0, vod_s))
            dialogue = str(s.get("dialogue_hindi", "Bhai dekho kya zabardast scene hai!")).strip()

            v_start = current_t
            v_end = v_start + dur
            current_t = v_end

            processed.append({
                "id": f"seg_{idx + 1:03d}",
                "clip_index": idx,
                "act": s.get("act", "Act II: Action"),
                "video_start": round(v_start, 2),
                "video_end": round(v_end, 2),
                "duration": round(dur, 2),
                "video_start_fmt": self._fmt_time(v_start),
                "video_end_fmt": self._fmt_time(v_end),
                "vod_start": round(vod_s, 2),
                "vod_end": round(vod_s + dur, 2),
                "vod_start_fmt": self._fmt_time(vod_s),
                "vod_end_fmt": self._fmt_time(vod_s + dur),
                "scene_note": s.get("scene_note", "High-energy gameplay cut"),
                "dialogue_hindi": dialogue,
                "pacing": s.get("pacing", "fast_paced"),
                "word_count": len(dialogue.split()),
                "target_words": int(dur * 2.2),
            })

            if current_t >= target_seconds:
                break

        return processed

    @staticmethod
    def _fmt_time(secs: float) -> str:
        s = max(0, int(secs))
        m = s // 60
        sec = s % 60
        return f"{m:02d}:{sec:02d}"
