"use client";

import React, { useState, useRef, useEffect } from "react";
import {
  X,
  Mic,
  Square,
  Upload,
  CheckCircle2,
  Sliders,
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
  const [scrollSpeed, setScrollSpeed] = useState<number>(30);

  const videoRef = useRef<HTMLVideoElement>(null);
  const teleprompterRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const scrollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scrollSpeedRef = useRef<number>(30);

  useEffect(() => {
    scrollSpeedRef.current = scrollSpeed;
  }, [scrollSpeed]);

  // Cleanup mic stream & timers on close/unmount
  useEffect(() => {
    if (!isOpen) {
      cleanupResources();
    }
    return () => cleanupResources();
  }, [isOpen]);

  const cleanupResources = () => {
    if (scrollIntervalRef.current) {
      clearInterval(scrollIntervalRef.current);
      scrollIntervalRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {}
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.pause();
    }
    setIsRecording(false);
  };

  if (!isOpen) return null;

  const startRecording = async () => {
    try {
      setUploadError(null);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";

      const mediaRecorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: mimeType || "audio/webm" });
        setRecordedBlob(audioBlob);
        setRecordedUrl(URL.createObjectURL(audioBlob));
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      };

      mediaRecorder.start(250);
      setIsRecording(true);

      if (videoRef.current) {
        videoRef.current.currentTime = 0;
        videoRef.current.volume = 0.15;
        videoRef.current.play().catch(() => {});
      }

      if (teleprompterRef.current) {
        teleprompterRef.current.scrollTop = 0;
      }

      if (scrollIntervalRef.current) clearInterval(scrollIntervalRef.current);
      scrollIntervalRef.current = setInterval(() => {
        if (teleprompterRef.current) {
          teleprompterRef.current.scrollTop += scrollSpeedRef.current / 20;
        }
      }, 50);
    } catch (err) {
      console.error("Microphone access error:", err);
      setUploadError("Mic permission denied. Allow mic access or upload an audio file.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
    if (videoRef.current) videoRef.current.pause();
    if (scrollIntervalRef.current) {
      clearInterval(scrollIntervalRef.current);
      scrollIntervalRef.current = null;
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
      setUploadError(err.message || "Failed to mix voiceover");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-xl flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
      <div className="w-full max-w-5xl bg-studio-900 border border-studio-700 rounded-3xl shadow-2xl flex flex-col overflow-hidden max-h-[92vh]">
        {/* Top Bar */}
        <div className="px-5 py-3.5 border-b border-studio-800 flex items-center justify-between bg-studio-950/80">
          <div className="flex items-center gap-2.5">
            <Mic className="w-4 h-4 text-[#FF4655]" />
            <h2 className="text-sm font-extrabold text-white">Teleprompter Voiceover Studio</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-xl text-slate-400 hover:text-white hover:bg-studio-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 p-5 flex-1 overflow-y-auto">
          {/* Left: Video + Controls */}
          <div className="lg:col-span-5 flex flex-col space-y-3">
            <div className="relative aspect-video rounded-2xl overflow-hidden bg-black border border-studio-700">
              <video
                ref={videoRef}
                src={getFullMediaUrl(videoUrl)}
                playsInline
                className="w-full h-full object-contain"
              />
            </div>

            <div className="p-4 rounded-2xl bg-studio-950 border border-studio-800 space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-slate-300">Status</span>
                {isRecording ? (
                  <span className="flex items-center gap-1.5 font-mono font-bold text-rose-400">
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                    RECORDING
                  </span>
                ) : recordedBlob ? (
                  <span className="font-mono text-emerald-400 flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Ready to Mix
                  </span>
                ) : (
                  <span className="text-slate-500">Idle</span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {!isRecording ? (
                  <button
                    type="button"
                    onClick={startRecording}
                    className="flex-1 py-2.5 px-4 rounded-xl bg-[#FF4655] hover:brightness-110 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
                  >
                    <Mic className="w-4 h-4" />
                    <span>Start Recording</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={stopRecording}
                    className="flex-1 py-2.5 px-4 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
                  >
                    <Square className="w-4 h-4 fill-current" />
                    <span>Stop</span>
                  </button>
                )}

                <label
                  className="p-2.5 rounded-xl bg-studio-800 hover:bg-studio-700 text-slate-300 border border-studio-700 cursor-pointer flex items-center justify-center transition"
                  title="Upload MP3 / WAV"
                >
                  <Upload className="w-4 h-4" />
                  <input type="file" accept="audio/*" onChange={handleFileUpload} className="hidden" />
                </label>
              </div>

              {recordedUrl && (
                <div className="pt-2 border-t border-studio-800 space-y-2">
                  <audio src={recordedUrl} controls className="w-full h-8" />
                  <button
                    type="button"
                    onClick={handleSaveAndMix}
                    disabled={isUploading}
                    className="w-full py-2 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold text-xs transition disabled:opacity-50"
                  >
                    {isUploading ? "Mixing Voiceover..." : "Mix Voiceover & Export HD"}
                  </button>
                </div>
              )}

              {uploadError && <p className="text-xs text-rose-400 font-medium">{uploadError}</p>}
            </div>
          </div>

          {/* Right: Teleprompter Script */}
          <div className="lg:col-span-7 flex flex-col bg-studio-950 rounded-2xl border border-studio-800 overflow-hidden max-h-[55vh] lg:max-h-[65vh]">
            <div className="px-4 py-2.5 bg-studio-900 border-b border-studio-800 flex items-center justify-between">
              <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5 text-[#FF4655]" />
                Scroll Speed
              </span>
              <div className="flex items-center gap-1.5 text-xs">
                {[20, 30, 45, 60].map((spd) => (
                  <button
                    key={spd}
                    type="button"
                    onClick={() => setScrollSpeed(spd)}
                    className={`px-2 py-1 rounded-lg border font-mono font-bold transition ${
                      scrollSpeed === spd
                        ? "bg-[#FF4655] text-white border-[#FF4655]"
                        : "bg-studio-800 text-slate-400 border-studio-700 hover:text-white"
                    }`}
                  >
                    {spd === 20 ? "0.75x" : spd === 30 ? "1.0x" : spd === 45 ? "1.5x" : "2.0x"}
                  </button>
                ))}
              </div>
            </div>

            <div
              ref={teleprompterRef}
              className="flex-1 p-5 overflow-y-auto space-y-6"
            >
              {segments.map((seg, idx) => (
                <div key={seg.id} className="space-y-1.5 border-b border-studio-800/60 pb-5">
                  <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                    <span className="text-[#FF4655] font-bold">
                      [{seg.video_start_fmt} - {seg.video_end_fmt}]
                    </span>
                    <span className="text-amber-400/80 text-[10px]">{seg.act}</span>
                  </div>
                  <p className="text-lg font-bold text-slate-100 leading-relaxed">
                    "{seg.dialogue_hindi}"
                  </p>
                </div>
              ))}
              <div className="h-24" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
