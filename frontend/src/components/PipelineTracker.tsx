"use client";

import React from "react";
import { CheckCircle2 } from "lucide-react";
import { JobState } from "../types/recap";

interface PipelineTrackerProps {
  job: JobState;
}

const STAGES = [
  { stage: 1, title: "Full Video & Transcript" },
  { stage: 2, title: "Cutting 1080p Clips" },
  { stage: 3, title: "AI Watching Clips & Voice" },
  { stage: 4, title: "1080p Render & Captions" },
];

export default function PipelineTracker({ job }: PipelineTrackerProps) {
  const currentStage = job.stage || 1;
  const progressPct = Math.min(100, Math.max(0, job.progress || 5));

  return (
    <div className="w-full bg-studio-900 border border-studio-800 rounded-2xl p-4 shadow-xl space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-[#FF4655] animate-ping" />
          <span className="text-xs font-bold text-slate-200">
            {job.message || "Processing video recap..."}
          </span>
        </div>
        <span className="text-xs font-extrabold text-[#FF4655] font-mono">{progressPct}%</span>
      </div>

      <div className="w-full bg-studio-950 h-1.5 rounded-full overflow-hidden border border-studio-800">
        <div
          className="bg-gradient-to-r from-[#FF4655] to-amber-400 h-full transition-all duration-300"
          style={{ width: `${progressPct}%` }}
        />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
        {STAGES.map((s) => {
          const isDone = currentStage > s.stage || job.status === "COMPLETED";
          const isCurrent = currentStage === s.stage && job.status !== "FAILED" && !isDone;

          return (
            <div
              key={s.stage}
              className={`p-2 rounded-xl text-center border text-[11px] font-bold transition flex items-center justify-center gap-1.5 ${
                isDone
                  ? "bg-studio-950 text-emerald-400 border-emerald-500/30"
                  : isCurrent
                  ? "bg-studio-800 text-white border-[#FF4655]"
                  : "bg-studio-950/40 text-slate-600 border-studio-900"
              }`}
            >
              {isDone ? <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" /> : null}
              <span>{s.title}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
