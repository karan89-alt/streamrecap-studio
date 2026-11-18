"use client";

import React from "react";
import { X, Download, Volume2, Subtitles, CheckCircle2 } from "lucide-react";
import { getDownloadUrl } from "../lib/api";
import { JobState } from "../types/recap";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  job: JobState;
}

export default function ExportModal({ isOpen, onClose, job }: ExportModalProps) {
  if (!isOpen) return null;

  const finalVideoUrl = getDownloadUrl(job.final_video_url || job.stitched_video_url || "");
  const gameAudioUrl = job.game_audio_video_url ? getDownloadUrl(job.game_audio_video_url) : "";
  const srtUrl = job.srt_url ? getDownloadUrl(job.srt_url) : "";

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-studio-900 border border-studio-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-studio-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <h3 className="text-sm font-bold text-white">1080p Full HD Recap Ready</h3>
          </div>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-3">
          {/* Main Full HD Video with Sarvam AI Voice + Viral Subtitles */}
          <div className="p-4 rounded-xl bg-studio-950 border border-emerald-500/30 flex items-center justify-between gap-3">
            <div>
              <h4 className="text-xs font-bold text-white">1080p Full HD Video (Sarvam AI Voice + Viral Captions)</h4>
              <p className="text-[11px] text-slate-400">Audio-synced 1080p cuts with Indian AI narration</p>
            </div>
            <a
              href={finalVideoUrl}
              download={`StreamRecap_${job.id}_1080p.mp4`}
              className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold text-xs flex items-center gap-1.5 shrink-0"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download</span>
            </a>
          </div>

          {/* Original Game Audio Track */}
          {gameAudioUrl && (
            <div className="p-4 rounded-xl bg-studio-950 border border-studio-800 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-xs font-bold text-slate-200">Original Game Audio (.M4A)</h4>
                <p className="text-[11px] text-slate-400">Synced background game SFX track</p>
              </div>
              <a
                href={gameAudioUrl}
                download={`StreamRecap_${job.id}_game_audio.m4a`}
                className="px-3 py-1.5 rounded-lg bg-studio-800 hover:bg-studio-700 text-white font-bold text-xs flex items-center gap-1.5 border border-studio-700 shrink-0"
              >
                <Volume2 className="w-3.5 h-3.5" />
                <span>Audio</span>
              </a>
            </div>
          )}

          {/* SRT Subtitles */}
          {srtUrl && (
            <div className="p-4 rounded-xl bg-studio-950 border border-studio-800 flex items-center justify-between gap-3">
              <div>
                <h4 className="text-xs font-bold text-slate-200">Hindi Subtitles (.SRT)</h4>
                <p className="text-[11px] text-slate-400">Audio-synced for YouTube CC</p>
              </div>
              <a
                href={srtUrl}
                download={`subtitles_${job.id}.srt`}
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
            type="button"
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
