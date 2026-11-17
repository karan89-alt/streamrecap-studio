"use client";

import React, { useRef, useState, useEffect } from "react";
import {
  Play,
  Pause,
  Maximize2,
  Tv,
  Volume2,
  VolumeX,
  Radio,
} from "lucide-react";
import { getFullMediaUrl } from "../lib/api";
import { ScriptSegment } from "../types/recap";

interface VideoStudioProps {
  videoUrl: string;
  activeSegment?: ScriptSegment;
  currentTime: number;
  onTimeUpdate: (time: number) => void;
  videoRef: React.RefObject<HTMLVideoElement>;
}

export default function VideoStudio({
  videoUrl,
  activeSegment,
  currentTime,
  onTimeUpdate,
  videoRef,
}: VideoStudioProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  // Requirement: Button to on/off original audio, by default that will be OFF (muted)
  const [isOriginalAudioOn, setIsOriginalAudioOn] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const fullVideoUrl = getFullMediaUrl(videoUrl);

  // Set initial muted state when video loads
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.muted = !isOriginalAudioOn;
    }
  }, [isOriginalAudioOn, videoUrl]);

  const togglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
    } else {
      videoRef.current.play().catch(() => {});
    }
    setIsPlaying(!isPlaying);
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      onTimeUpdate(time);
    }
  };

  const toggleOriginalAudio = () => {
    const nextState = !isOriginalAudioOn;
    setIsOriginalAudioOn(nextState);
    if (videoRef.current) {
      videoRef.current.muted = !nextState;
      videoRef.current.volume = 1.0;
    }
  };

  const toggleFullscreen = () => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().catch((err) => console.error(err));
    } else {
      document.exitFullscreen();
    }
  };

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div
      ref={containerRef}
      className="w-full bg-black rounded-2xl overflow-hidden border border-studio-800 shadow-2xl relative flex flex-col group"
    >
      {/* Main Video Viewport */}
      <div className="relative aspect-video w-full bg-studio-950 flex items-center justify-center overflow-hidden">
        <video
          ref={videoRef}
          src={fullVideoUrl}
          playsInline
          muted={!isOriginalAudioOn}
          className="w-full h-full object-contain"
          onTimeUpdate={() => {
            if (videoRef.current) {
              onTimeUpdate(videoRef.current.currentTime);
            }
          }}
          onLoadedMetadata={() => {
            if (videoRef.current) {
              setDuration(videoRef.current.duration);
              videoRef.current.muted = !isOriginalAudioOn;
            }
          }}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
        />

        {/* Top Minimal Badges */}
        <div className="absolute top-3 left-3 right-3 flex items-center justify-between pointer-events-none z-20">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-black/80 border border-white/10 text-[11px] font-bold text-white">
            <Tv className="w-3.5 h-3.5 text-[#FF4655]" />
            <span>1080p Full HD</span>
          </div>

          {activeSegment && (
            <div className="px-2.5 py-1 rounded-lg bg-black/80 border border-amber-400/30 text-[11px] font-bold text-amber-300">
              {activeSegment.act}
            </div>
          )}
        </div>

        {/* Viral Font Style Captions on Video */}
        {activeSegment && (
          <div className="absolute bottom-12 left-4 right-4 text-center pointer-events-none z-20 transition-all">
            <div className="inline-block max-w-2xl px-4 py-2 rounded-xl bg-black/75 backdrop-blur-sm border border-white/15">
              <p
                className="text-base sm:text-xl md:text-2xl font-black uppercase tracking-wide text-[#FFE600] leading-snug"
                style={{
                  textShadow: "2px 2px 0 #000, -2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 0 4px 8px rgba(0,0,0,0.8)",
                  fontFamily: "Impact, Arial Black, sans-serif"
                }}
              >
                {activeSegment.dialogue_hindi}
              </p>
            </div>
          </div>
        )}

        {/* Center Play Button Overlay */}
        {!isPlaying && (
          <button
            onClick={togglePlay}
            className="absolute z-10 w-14 h-14 rounded-full bg-[#FF4655] text-white flex items-center justify-center shadow-2xl hover:scale-105 active:scale-95 transition"
          >
            <Play className="w-6 h-6 translate-x-0.5 fill-current" />
          </button>
        )}
      </div>

      {/* Sleek Minimal Control Bar */}
      <div className="w-full bg-studio-900 border-t border-studio-800 p-3 flex flex-col gap-2">
        {/* Scrubber */}
        <input
          type="range"
          min={0}
          max={duration || 100}
          step={0.1}
          value={currentTime}
          onChange={handleSeek}
          className="w-full h-1.5 bg-studio-800 rounded-lg appearance-none cursor-pointer accent-[#FF4655]"
        />

        {/* Controls Row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlay}
              className="w-8 h-8 rounded-lg bg-studio-800 hover:bg-studio-700 text-white flex items-center justify-center transition"
            >
              {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 translate-x-0.5" />}
            </button>

            <span className="text-xs font-mono text-slate-300">
              <span className="text-white font-bold">{formatTime(currentTime)}</span> / {formatTime(duration)}
            </span>
          </div>

          <div className="flex items-center gap-2.5">
            {/* Requirement: Button to on/off original audio, by default that will be OFF */}
            <button
              onClick={toggleOriginalAudio}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 border transition ${
                isOriginalAudioOn
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/40"
                  : "bg-studio-950 text-slate-400 border-studio-800 hover:text-slate-200"
              }`}
            >
              {isOriginalAudioOn ? (
                <>
                  <Volume2 className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                  <span>Original Audio: ON</span>
                </>
              ) : (
                <>
                  <VolumeX className="w-3.5 h-3.5" />
                  <span>Original Audio: OFF</span>
                </>
              )}
            </button>

            {/* Fullscreen */}
            <button onClick={toggleFullscreen} className="text-slate-400 hover:text-white p-1">
              <Maximize2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
