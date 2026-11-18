import { JobState, ScriptSegment } from "../types/recap";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://streamrecap-studio-production.up.railway.app";
const SARVAM_KEY = process.env.NEXT_PUBLIC_SARVAM_API_KEY || "";

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    return await res.json();
  } catch (e) {
    return { status: "offline", error: String(e) };
  }
}

export async function startRecap(
  url: string,
  target_minutes: number,
  story_style: string,
  voice_speaker: string = "shubh",
  playback_speed: number = 1.0
) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (SARVAM_KEY) {
    headers["X-Sarvam-Key"] = SARVAM_KEY;
  }

  const res = await fetch(`${API_BASE}/api/recap/generate`, {
    method: "POST",
    headers,
    body: JSON.stringify({ url, target_minutes, story_style, voice_speaker, playback_speed }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Failed to start recap");
  }
  return await res.json();
}

export async function fetchJob(jobId: string): Promise<JobState> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
  if (!res.ok) {
    throw new Error("Job not found");
  }
  return await res.json();
}

export function subscribeJobEvents(jobId: string, onUpdate: (data: Partial<JobState>) => void) {
  const eventSource = new EventSource(`${API_BASE}/api/jobs/${jobId}/events`);
  eventSource.addEventListener("status", (event) => {
    try {
      const data = JSON.parse(event.data);
      onUpdate(data);
    } catch (e) {
      console.error("Error parsing SSE event:", e);
    }
  });
  return () => {
    eventSource.close();
  };
}

export async function updateScript(jobId: string, segments: ScriptSegment[]) {
  const res = await fetch(`${API_BASE}/api/recap/${jobId}/script/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ segments }),
  });
  if (!res.ok) {
    throw new Error("Failed to update script");
  }
  return await res.json();
}

export async function uploadRecordedVoice(
  jobId: string,
  audioBlob: Blob,
  gameVolume: number = 0.15
) {
  const formData = new FormData();
  formData.append("audio_file", audioBlob, "recorded_voice.webm");
  formData.append("game_volume", gameVolume.toString());

  const res = await fetch(`${API_BASE}/api/recap/${jobId}/voice/record`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    throw new Error("Failed to upload voiceover");
  }
  return await res.json();
}

export const uploadUserVoice = uploadRecordedVoice;

export function getFullMediaUrl(pathOrUrl: string): string {
  if (!pathOrUrl) return "";
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  return `${API_BASE}${pathOrUrl.startsWith("/") ? "" : "/"}${pathOrUrl}`;
}

export function getDownloadUrl(pathOrUrl: string): string {
  if (!pathOrUrl) return "";
  const filename = pathOrUrl.split("/").pop() || "";
  if (!filename) return getFullMediaUrl(pathOrUrl);
  return `${API_BASE}/api/download/${encodeURIComponent(filename)}`;
}
