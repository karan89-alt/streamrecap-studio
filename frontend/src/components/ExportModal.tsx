"use client";

import React from "react";
import { X, Download, Film, Subtitles, CheckCircle2 } from "lucide-react";
import { getFullMediaUrl } from "../lib/api";
import { JobState } from "../types/recap";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  job: JobState;
}

export default function ExportModal({ isOpen, onClose, job }: ExportModalProps) {
  if (!isOpen) return null;

  const finalVideoUrl = getFullMediaUrl(job.final_video_url || job.stitched_video_url || "");
  const masterVideoUrl = getFullMediaUrl(job.stitched_video_url || "");
  const srtUrl = getFullMediaUrl(job.srt_url || "");

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-studio-900 border border-studio-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-studio-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <h3 className="text-sm font-bold text-white">Full HD Video Ready</h3>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-3">
          {/* Main Full HD Video with Viral Subtitles */}
          <div className="p-4 rounded-xl bg-studio-950 border border-emerald-500/30 flex items-center justify-between gap-3">
            <div>
              <h4 className="text-xs font-bold text-white">1080p Full HD Video (Viral Captions + Original Audio)</h4>
              <p className="text-[11px] text-slate-400">Complete video recap with viral yellow captions</p>
            </div>
            <a
              href={finalVideoUrl}
              download={`StreamRecap_${job.id}_1080p.mp4`}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold text-xs flex items-center gap-1.5 shrink-0"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download</span>
            </a>
          </div>

          {/* Raw Stitched Clips */}
          <div className="p-4 rounded-xl bg-studio-950 border border-studio-800 flex items-center justify-between gap-3">
            <div>
              <h4 className="text-xs font-bold text-slate-200">Raw Stitched Video (Clean Game Audio)</h4>
              <p className="text-[11px] text-slate-400">Raw 1080p clips without burned captions</p>
            </div>
            <a
              href={masterVideoUrl}
              download={`StreamRecap_${job.id}_raw.mp4`}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 rounded-lg bg-studio-800 hover:bg-studio-700 text-white font-bold text-xs flex items-center gap-1.5 border border-studio-700 shrink-0"
            >
              <Film className="w-3.5 h-3.5" />
              <span>Download</span>
            </a>
          </div>

          {/* SRT Subtitles */}
          {job.srt_url && (
            <div className="p-4 rounded-xl bg-studio-950 border border-studio-800 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-xs font-bold text-slate-200">Hindi Subtitles (.SRT)</h4>
                <p className="text-[11px] text-slate-400">Timestamped for YouTube CC & premiere</p>
              </div>
              <a
                href={srtUrl}
                download={`subtitles_${job.id}.srt`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 rounded-lg bg-studio-800 hover:bg-studio-700 text-slate-200 font-bold text-xs flex items-center gap-1.5 border border-studio-700 shrink-0"
              >
                <Subtitles className="w-3.5 h-3.5" />
                <span>SRT</span>
              </a>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 bg-studio-950 border-t border-studio-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-studio-800 hover:bg-studio-700 text-white font-bold text-xs"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
