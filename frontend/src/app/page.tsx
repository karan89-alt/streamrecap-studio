"use client";

import React, { useState, useRef, useEffect } from "react";
import Header from "../components/Header";
import InputConfigBar from "../components/InputConfigBar";
import PipelineTracker from "../components/PipelineTracker";
import VideoStudio from "../components/VideoStudio";
import SyncedScriptList from "../components/SyncedScriptList";
import TeleprompterModal from "../components/TeleprompterModal";
import ExportModal from "../components/ExportModal";
import { JobState, ScriptSegment } from "../types/recap";
import { startRecap, fetchJob, subscribeJobEvents } from "../lib/api";
import { Mic, Download, AlertTriangle } from "lucide-react";

export default function HomePage() {
  const [job, setJob] = useState<JobState | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);

  const [isTeleprompterOpen, setIsTeleprompterOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const sseCleanupRef = useRef<(() => void) | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopTracking = () => {
    if (sseCleanupRef.current) {
      sseCleanupRef.current();
      sseCleanupRef.current = null;
    }
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    return () => stopTracking();
  }, []);

  const handleStartRecap = async (
    url: string,
    targetMinutes: number,
    storyStyle: string
  ) => {
    stopTracking();
    setIsProcessing(true);
    setCurrentTime(0);

    try {
      const res = await startRecap(url, targetMinutes, storyStyle);
      const newJobId = res.job_id;

      setJob({
        id: newJobId,
        url,
        target_minutes: targetMinutes,
        story_style: storyStyle,
        status: "PROCESSING",
        stage: 1,
        progress: 8,
        message: "Analyzing stream & writing script...",
      });

      // Real-time SSE updates
      sseCleanupRef.current = subscribeJobEvents(newJobId, (updated) => {
        setJob((prev) => {
          const merged = prev ? { ...prev, ...updated } : (updated as JobState);
          if (merged.status === "COMPLETED" || merged.status === "FAILED") {
            setIsProcessing(false);
            stopTracking();
          }
          return merged;
        });
      });

      // Fallback polling every 3s
      pollIntervalRef.current = setInterval(async () => {
        try {
          const fresh = await fetchJob(newJobId);
          setJob(fresh);
          if (fresh.status === "COMPLETED" || fresh.status === "FAILED") {
            setIsProcessing(false);
            stopTracking();
          }
        } catch {
          // Transient network hiccup — wait for next tick
        }
      }, 3000);
    } catch (err: any) {
      setJob({
        id: "err",
        url,
        target_minutes: targetMinutes,
        story_style: storyStyle,
        status: "FAILED",
        stage: 0,
        progress: 0,
        message: err.message || "Could not connect to server",
        error: err.message || String(err),
      });
      setIsProcessing(false);
    }
  };

  const handleJumpToTime = (time: number) => {
    setCurrentTime(time);
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      videoRef.current.play().catch(() => {});
    }
  };

  const handleSegmentsUpdated = (updated: ScriptSegment[]) => {
    if (job) {
      setJob({ ...job, segments: updated });
    }
  };

  const handleExportSuccess = (finalUrl: string) => {
    if (job) {
      setJob({
        ...job,
        final_video_url: finalUrl,
        status: "COMPLETED",
        voice_mode: "SELF_RECORDED",
      });
      setIsExportOpen(true);
    }
  };

  const activeSegment = job?.segments?.find(
    (s) => currentTime >= s.video_start && currentTime < s.video_end
  );

  return (
    <div className="min-h-screen bg-[#090A0F] text-slate-100 flex flex-col font-sans">
      <Header />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-5 space-y-5">
        {/* Input & Configuration Bar */}
        <InputConfigBar onGenerate={handleStartRecap} isProcessing={isProcessing} />

        {/* Live Processing Pipeline Tracker */}
        {job && (isProcessing || job.status === "PROCESSING" || job.status === "QUEUED") && (
          <PipelineTracker job={job} />
        )}

        {/* Clear Error Banner if Job Fails */}
        {job && job.status === "FAILED" && (
          <div className="w-full bg-rose-950/40 border border-rose-500/40 rounded-2xl p-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />
              <div>
                <p className="text-xs font-bold text-rose-300">Processing Failed</p>
                <p className="text-xs text-rose-200/80">{job.error || job.message}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => handleStartRecap(job.url, job.target_minutes, job.story_style)}
              className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shrink-0"
            >
              Retry
            </button>
          </div>
        )}

        {/* Studio Workspace */}
        {job &&
          job.status === "COMPLETED" &&
          job.segments &&
          job.segments.length > 0 &&
          (job.final_video_url || job.stitched_video_url) && (
            <div className="space-y-4">
              {/* Minimal Studio Action Bar */}
              <div className="w-full bg-studio-900 border border-studio-800 rounded-2xl px-4 py-3 flex items-center justify-between gap-3 shadow-lg">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    {job.story_style} • {job.target_minutes} Min • 1080p Full HD
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIsTeleprompterOpen(true)}
                    className="px-3 py-1.5 rounded-xl bg-studio-800 hover:bg-studio-700 text-white font-bold text-xs flex items-center gap-1.5 border border-studio-700 transition"
                  >
                    <Mic className="w-3.5 h-3.5 text-[#FF4655]" />
                    <span>Teleprompter Mic</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setIsExportOpen(true)}
                    className="px-4 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold text-xs flex items-center gap-1.5 transition"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download Video</span>
                  </button>
                </div>
              </div>

              {/* Split View: Video (Left) + Synced Hindi Script (Right) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
                <div className="lg:col-span-7">
                  <VideoStudio
                    videoUrl={job.final_video_url || job.stitched_video_url || ""}
                    activeSegment={activeSegment}
                    currentTime={currentTime}
                    onTimeUpdate={setCurrentTime}
                    videoRef={videoRef}
                  />
                </div>

                <div className="lg:col-span-5">
                  <SyncedScriptList
                    jobId={job.id}
                    segments={job.segments}
                    currentTime={currentTime}
                    onJumpToTime={handleJumpToTime}
                    onSegmentsUpdated={handleSegmentsUpdated}
                  />
                </div>
              </div>
            </div>
          )}
      </main>

      {/* Modals */}
      {job && (
        <>
          <TeleprompterModal
            isOpen={isTeleprompterOpen}
            onClose={() => setIsTeleprompterOpen(false)}
            jobId={job.id}
            videoUrl={job.final_video_url || job.stitched_video_url || ""}
            segments={job.segments || []}
            onExportSuccess={handleExportSuccess}
          />

          <ExportModal
            isOpen={isExportOpen}
            onClose={() => setIsExportOpen(false)}
            job={job}
          />
        </>
      )}
    </div>
  );
}
