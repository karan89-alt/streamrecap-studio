"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  X,
  Mic,
  Square,
  Play,
  RotateCcw,
  Upload,
  Volume2,
  CheckCircle2,
  Radio,
  Sliders,
  ChevronDown
} from "lucide-react";
import { ScriptSegment } from "../types/recap";
import { uploadUserVoice, getFullMediaUrl } from "../lib/api";

interface TeleprompterModalProps {
  isOpen: boolean;
  onClose: () => void;
  jobId: string;
  videoUrl: string;
  segments: ScriptSegment[];
  onExportSuccess: (finalUrl: string) => void;
}

export default function TeleprompterModal({
  isOpen,
  onClose,
  jobId,
  videoUrl,
  segments,
  onExportSuccess,
}: TeleprompterModalProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [recordedUrl, setRecordedUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [scrollSpeed, setScrollSpeed] = useState<number>(30); // pixels per sec
  const [currentTime, setCurrentTime] = useState(0);

  const videoRef = useRef<HTMLVideoElement>(null);
  const teleprompterRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const scrollIntervalRef = useRef<any>(null);

  if (!isOpen) return null;

  const startRecording = async () => {
    try {
      setUploadError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        setRecordedBlob(audioBlob);
        setRecordedUrl(URL.createObjectURL(audioBlob));
        stream.getTracks().forEach((t) => t.stop());
      };

      mediaRecorder.start(250);
      setIsRecording(true);

      // Play video with game audio lowered to 15%
      if (videoRef.current) {
        videoRef.current.currentTime = 0;
        videoRef.current.volume = 0.15;
        videoRef.current.play();
      }

      // Start teleprompter smooth scrolling
      if (teleprompterRef.current) {
        teleprompterRef.current.scrollTop = 0;
      }
      scrollIntervalRef.current = setInterval(() => {
        if (teleprompterRef.current) {
          teleprompterRef.current.scrollTop += scrollSpeed / 20;
        }
      }, 50);
    } catch (err) {
      console.error("Microphone access error:", err);
      setUploadError("Could not access microphone. Please grant permission or upload an audio file.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
    if (videoRef.current) {
      videoRef.current.pause();
    }
    if (scrollIntervalRef.current) {
      clearInterval(scrollIntervalRef.current);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setRecordedBlob(file);
      setRecordedUrl(URL.createObjectURL(file));
    }
  };

  const handleSaveAndMix = async () => {
    if (!recordedBlob) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const res = await uploadUserVoice(jobId, recordedBlob);
      if (res.final_video_url) {
        onExportSuccess(res.final_video_url);
        onClose();
      }
    } catch (err: any) {
      setUploadError(err.message || "Failed to process voiceover");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-xl flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
      <div className="w-full max-w-5xl bg-studio-900 border border-studio-700 rounded-3xl shadow-2xl flex flex-col overflow-hidden max-h-[92vh]">
        {/* Modal Top Bar */}
        <div className="px-6 py-4 border-b border-studio-800 flex items-center justify-between bg-studio-950/80">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-brand-accent/20 border border-brand-accent/40 flex items-center justify-center text-brand-accent">
              <Mic className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-white flex items-center gap-2">
                <span>Self-Voiceover Studio & Teleprompter</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 uppercase font-mono">
                  Live Mic Mode
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Read live while video plays with 15% ducked game audio. Backend applies broadcast EBU loudnorm.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-studio-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body: Split View (Video + Teleprompter) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 p-6 flex-1 overflow-y-auto">
          {/* Left: Video Preview with 15% Game Audio Ducking (5 cols) */}
          <div className="lg:col-span-5 flex flex-col space-y-4">
            <div className="relative aspect-video rounded-2xl overflow-hidden bg-black border border-studio-700 shadow-xl">
              <video
                ref={videoRef}
                src={getFullMediaUrl(videoUrl)}
                className="w-full h-full object-contain"
                onTimeUpdate={() => {
                  if (videoRef.current) setCurrentTime(videoRef.current.currentTime);
                }}
              />
              {/* Overlay Ducking Status */}
              <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-black/80 backdrop-blur-md border border-brand-yellow/30 text-[11px] font-medium text-amber-300">
                <Radio className="w-3.5 h-3.5 animate-pulse text-amber-400" />
                <span>Game Audio: 15% Ducked</span>
              </div>
            </div>

            {/* Mic Recording Controls */}
            <div className="p-4 rounded-2xl bg-studio-950 border border-studio-800 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                  <Mic className="w-3.5 h-3.5 text-brand-accent" />
                  Recording Status:
                </span>
                {isRecording ? (
                  <span className="flex items-center gap-1.5 text-xs font-mono font-bold text-rose-400">
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                    RECORDING LIVE...
                  </span>
                ) : recordedBlob ? (
                  <span className="text-xs font-mono text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Audio Captured
                  </span>
                ) : (
                  <span className="text-xs text-slate-500">Ready to record</span>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2">
                {!isRecording ? (
                  <button
                    onClick={startRecording}
                    className="flex-1 py-2.5 px-4 rounded-xl bg-brand-accent hover:bg-brand-accent/90 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-brand-accent/25 transition active:scale-95"
                  >
                    <Mic className="w-4 h-4" />
                    <span>Start Teleprompter Recording</span>
                  </button>
                ) : (
                  <button
                    onClick={stopRecording}
                    className="flex-1 py-2.5 px-4 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs flex items-center justify-center gap-2 shadow-lg shadow-rose-600/30 transition active:scale-95"
                  >
                    <Square className="w-4 h-4 fill-current" />
                    <span>Stop Recording</span>
                  </button>
                )}

                {/* Upload audio file alternative */}
                <label className="p-2.5 rounded-xl bg-studio-800 hover:bg-studio-700 text-slate-300 border border-studio-700 cursor-pointer flex items-center justify-center transition" title="Upload Audio File">
                  <Upload className="w-4 h-4" />
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                </label>
              </div>

              {/* Audio Playback Preview if recorded */}
              {recordedUrl && (
                <div className="pt-2 border-t border-studio-800">
                  <p className="text-[11px] text-slate-400 mb-1">Your Voiceover Recording Preview:</p>
                  <audio src={recordedUrl} controls className="w-full h-8" />
                </div>
              )}

              {uploadError && (
                <p className="text-xs text-rose-400 font-medium">{uploadError}</p>
              )}
            </div>
          </div>

          {/* Right: Smooth Scrolling Teleprompter Window (7 cols) */}
          <div className="lg:col-span-7 flex flex-col bg-studio-950 rounded-2xl border border-studio-800 overflow-hidden relative shadow-inner">
            {/* Teleprompter Header & Controls */}
            <div className="px-4 py-3 bg-studio-900 border-b border-studio-800 flex items-center justify-between">
              <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-brand-cyan" />
                Teleprompter Speed:
              </span>
              <div className="flex items-center gap-2 text-xs">
                {[20, 30, 45, 60].map((spd) => (
                  <button
                    key={spd}
                    onClick={() => setScrollSpeed(spd)}
                    className={`px-2.5 py-1 rounded-lg border font-mono font-bold transition ${
                      scrollSpeed === spd
                        ? "bg-brand-accent text-white border-brand-accent"
                        : "bg-studio-800 text-slate-400 border-studio-700 hover:text-white"
                    }`}
                  >
                    {spd === 20 ? "0.75x" : spd === 30 ? "1.0x" : spd === 45 ? "1.5x" : "2.0x"}
                  </button>
                ))}
              </div>
            </div>

            {/* Scrollable Script Area */}
            <div
              ref={teleprompterRef}
              className="flex-1 p-6 overflow-y-auto space-y-8 scroll-smooth teleprompter-text"
            >
              <div className="h-10" />
              {segments.map((seg, idx) => (
                <div
                  key={seg.id}
                  className="space-y-2 border-b border-studio-800/60 pb-6 group hover:bg-studio-900/40 p-3 rounded-xl transition"
                >
                  <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                    <span className="text-brand-accent font-bold">
                      Scene {idx + 1} [{seg.video_start_fmt} - {seg.video_end_fmt}]
                    </span>
                    <span className="text-amber-400/80 uppercase font-semibold text-[10px]">
                      {seg.act}
                    </span>
                  </div>

                  <p className="text-lg sm:text-xl font-bold text-slate-100 leading-relaxed font-sans group-hover:text-amber-200 transition">
                    "{seg.dialogue_hindi}"
                  </p>

                  <p className="text-xs text-slate-500 italic">
                    Visual Cue: {seg.scene_note}
                  </p>
                </div>
              ))}
              <div className="h-40" />
            </div>
          </div>
        </div>

        {/* Modal Footer: Save & Mix Button */}
        <div className="px-6 py-4 bg-studio-950 border-t border-studio-800 flex items-center justify-between">
          <p className="text-xs text-slate-400">
            Clicking merge will duck game audio to 15% and mix your voice with loudnorm broadcast compression.
          </p>

          <button
            onClick={handleSaveAndMix}
            disabled={!recordedBlob || isUploading}
            className={`px-6 py-2.5 rounded-xl font-bold text-xs tracking-wide flex items-center gap-2 transition ${
              recordedBlob && !isUploading
                ? "bg-gradient-to-r from-emerald-500 to-teal-500 hover:brightness-110 text-white shadow-lg shadow-emerald-500/20 active:scale-95"
                : "bg-studio-800 text-slate-500 cursor-not-allowed border border-studio-700"
            }`}
          >
            {isUploading ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Mixing Voiceover with Game Audio...</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-4 h-4" />
                <span>Mix & Export Final Video</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
