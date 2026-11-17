# Railway Deployment Guide for StreamRecap Studio Backend

This guide explains how to host your FastAPI video processing backend on Railway with high-speed datacenter bandwidth and scalable RAM/CPU.

---

## 1. Prerequisites
- A free or pro [Railway.app](https://railway.app) account.
- A GitHub account with this repository pushed to it.

---

## 2. What Railway Provides Automatically
- **1 Gbps+ Enterprise Bandwidth**: YouTube video stream downloads and clip cuts will execute 5x to 10x faster than on home broadband.
- **Dedicated Cloud RAM & CPU**: Video rendering will not consume your local laptop/PC CPU or memory.
- **Pre-configured Dockerfile**: We have already created `backend/Dockerfile` with `ffmpeg`, Python 3.11, and all dependencies.

---

## 3. Step-by-Step Deployment Instructions

### Step A: Push Your Code to GitHub
In your project root (`c:\gta live stream`), push your files to a GitHub repository:
```bash
git init
git add .
git commit -m "StreamRecap Studio ready for Railway deployment"
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
git push -u origin main
```

### Step B: Create a New Project on Railway
1. Open [Railway Dashboard](https://railway.app/dashboard).
2. Click **"+ New Project"**.
3. Select **"Deploy from GitHub repo"**.
4. Choose your repository (`<YOUR_REPO>`).
5. In the service settings:
   - **Root Directory**: Set to `/backend` (so Railway builds from the backend folder).
   - Railway will automatically detect `Dockerfile` and start building.

### Step C: Add Environment Variables in Railway
1. Click on your deployed service in Railway.
2. Navigate to the **"Variables"** tab.
3. Add the following variables:
   - `PORT`: `8000`
   - `GEMINI_API_KEY`: `<Your Gemini API Key>` (or `OPENAI_API_KEY`)
   - `FFMPEG_PATH`: `ffmpeg` (the Docker container already has ffmpeg on system PATH)
   - `FFPROBE_PATH`: `ffprobe`

### Step D: Generate a Public Domain
1. In the Railway service dashboard, go to the **"Settings"** tab.
2. Under **"Networking"**, click **"Generate Domain"**.
3. You will receive a public HTTPS URL like:
   `https://streamrecap-production.up.railway.app`

### Step E: Connect Your Frontend to Railway
In your frontend `.env.local` or Next.js hosting (e.g., Vercel):
```env
NEXT_PUBLIC_API_URL=https://streamrecap-production.up.railway.app
```
That's it! Now all video clipping, AI narrative generation, and Full HD rendering will run entirely on Railway's cloud infrastructure!
