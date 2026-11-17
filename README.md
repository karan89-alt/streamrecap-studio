# 🎬 StreamRecap Studio

> **Transform 4–6 hour YouTube gaming live streams & VODs (e.g., GTA V, Battlegrounds) into high-retention 15–25 minute "Movie-Explainer" videos with time-synced Hindi commentary, built-in Teleprompter recording, and 1-Click AI Hindi dubbing.**

---

## ⚡ Overview & Key Capabilities

**StreamRecap Studio** is a full-stack AI creator suite engineered specifically for gaming content creators and YouTube movie-explainer channels. Long 4- to 6-hour live streams contain incredible moments, but manually editing them down and writing time-synced commentary takes days. StreamRecap Studio automates this entire pipeline in minutes:

1. **Smart Partial Slicing (Zero 6-Hour Bloat):**
   - Never downloads full 20GB+ streams.
   - Extracts timestamps and chat hype density via `yt-dlp`.
   - AI arranges key scenes into a **3-Act Story Arc** (*The Hook* -> *The Chaos/Mission* -> *The Climax & Payoff*).
   - Downloads only the targeted 5–12s highlight intervals via `yt-dlp --download-sections`.

2. **YouTube Monetization & Policy Safeguards:**
   - **Clean 0–7s Intro Rule:** The first clip (`[00:00 - 00:08]`) strictly adheres to YouTube advertiser-friendly guidelines (zero graphic violence or profanity).
   - **Anti-Content-ID Transformative Editing:** Applies subtle `1.06x` scale/crop (`crop=iw*0.94:ih*0.94`) and frame re-encoding to prevent automated video fingerprint matching.
   - **In-Game Radio Music Suppression:** Filters radio frequencies (`highpass=120, lowpass=6500`) and ducks background audio to 15% to prevent in-game car radio songs from triggering copyright strikes.

3. **Strict Duration & Word Count Sync:**
   - Spoken Hindi commentary is calibrated to natural fast-paced gaming cadence (~**2.2 Hindi words per second**).
   - Commentary lines match segment lengths with precision.

4. **Dual Final Voiceover Modes:**
   - 🎙️ **Option A: "Record My Own Voice" (Built-in Teleprompter Mode):**
     - Plays video preview with game audio ducked to 15%.
     - Hindi script scrolls smoothly like a news teleprompter with speed control (`0.75x`, `1.0x`, `1.5x`, `2.0x`).
     - Records microphone live via `MediaRecorder` API or accepts audio file upload.
     - Backend normalizes audio with broadcast EBU `loudnorm` (`I=-16, TP=-1.5, LRA=11`) and mixes with game audio.
   - 🤖 **Option B: "1-Click AI Hindi Voiceover" (Auto Dub):**
     - Synthesizes energetic Hindi speech (`hi-IN-MadhurNeural` - energetic male / `hi-IN-SwaraNeural` - expressive female / optional ElevenLabs).
     - Aligns speech blocks to video timestamps and renders final `1080p` `.mp4` + `.srt` Hindi subtitles.

---

## 🛠️ Tech Stack

- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Lucide Icons (Dark Studio/Creator UI theme).
- **Backend:** Python FastAPI, Uvicorn, SSE (Server-Sent Events) for real-time progress, `yt-dlp`, FFmpeg 9.0+, `edge-tts`, `google-genai` / `openai`.
- **Audio & Video Processing:** FFmpeg with `libx264`, `loudnorm`, `amix`, `adelay`, and audio ducking.

---

## 🚀 Quick Start Guide

### Prerequisites
- **Node.js** v18+ and **npm**
- **Python** 3.10+
- **FFmpeg** (installed and detected automatically in `PATH` or WinGet)

---

### 1. Backend Setup

```bash
cd backend

# Create & activate virtual environment (Windows PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables (optional: add Gemini or OpenAI key)
cp .env.example .env

# Run FastAPI backend server
python main.py
```

The backend starts at: **`http://127.0.0.1:8000`**  
Interactive API Docs available at: **`http://127.0.0.1:8000/docs`**

---

### 2. Frontend Setup

In a new terminal window:

```bash
cd frontend

# Install npm packages
npm install

# Start Next.js development server
npm run dev
```

Open your browser at: **`http://localhost:3000`**

---

## ⚙️ Environment Configuration (`backend/.env`)

```env
# Optional AI Narrative API Keys (system includes high-octane procedural Hindi screenwriter as fallback)
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Optional ElevenLabs for voiceover (falls back to edge-tts Madhur/Swara)
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=

HOST=127.0.0.1
PORT=8000
DEBUG=True
```

---

## 🕹️ User Workflow

1. **Input & Configure:**
   - Paste any YouTube past live stream URL, or click **"GTA V 5-Star Heist"** for instant sample loading.
   - Choose Target Video Length (`15 Minutes`, `20 Minutes`, `25 Minutes`, or `3 Minutes Fast Preview`).
   - Choose Storytelling Style:
     - 🎭 **Dramatic Movie-Explainer:** Cinematic, suspenseful narrative with plot twists.
     - 🔥 **Funny Hindi Gaming Roast:** Sarcastic commentary roasting streamer fails & funny luck.
     - ⚡ **High-Tension Action Recap:** Fast adrenaline, police pursuits & clutch gunplay.
   - Click **"Generate Recap & Hindi Script"**.

2. **Watch Live Pipeline Tracker:**
   - Stage 1: Stream Analysis & Chat Hype Spikes detection.
   - Stage 2: AI structuring 3-Act Story Arc & time-synced Hindi dialogue.
   - Stage 3: Partial section download & FFmpeg 1080p stitching with 1.06x anti-Content-ID crop and radio suppression.
   - Stage 4: Ready for Voiceover!

3. **Studio Workspace & Script Editing:**
   - Watch the 1080p edited video preview with custom HTML5 studio controls.
   - Scrollable Hindi script panel auto-highlights and auto-scrolls with playback.
   - Click any script block to jump the video directly to that timestamp.
   - Click the pencil icon on any card to tweak commentary; word count indicator confirms ~2.2 words/second pacing.

4. **Export Your Creation:**
   - **Teleprompter Recording:** Record your voice live with ducked background game audio.
   - **1-Click AI Dub:** Auto-dub with Madhur or Swara neural voices.
   - **Download:** Final `.mp4`, stitched clips, and `.srt` Hindi subtitles.

---

## 🛡️ License
MIT License. Built for creators.
