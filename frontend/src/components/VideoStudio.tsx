"use client";

import React, { useRef, useState, useEffect } from "react";
import {
  Play,
  Pause,
  Maximize2,
  Tv,
  Volume2,
  VolumeX,
  Loader2,
} from "lucide-react";
import { getFullMediaUrl } from "../lib/api";
import { ScriptSegment } from "../types/recap";

interface VideoStudioProps {
  videoUrl: string;
  gameAudioUrl?: string;
  activeSegment?: ScriptSegment;
  currentTime: number;
  onTimeUpdate: (time: number) => void;
  videoRef: React.RefObject<HTMLVideoElement>;
}

export default function VideoStudio({
  videoUrl,
  gameAudioUrl,
  activeSegment,
  currentTime,
  onTimeUpdate,
  videoRef,
}: VideoStudioProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const [duration, setDuration] = useState(0);
  // Original Game Audio toggle: OFF by default (Sarvam AI Indian voice explains the whole video)
  const [isOriginalAudioOn, setIsOriginalAudioOn] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const gameAudioRef = useRef<HTMLAudioElement>(null);

  const fullVideoUrl = getFullMediaUrl(videoUrl);
  const fullGameAudioUrl = gameAudioUrl ? getFullMediaUrl(gameAudioUrl) : "";

  useEffect(() => {
    setIsPlaying(false);
    setDuration(0);
    setIsOriginalAudioOn(false);
  }, [fullVideoUrl]);

  // Keep optional original game audio in exact lockstep with the main video
  useEffect(() => {
    const ga = gameAudioRef.current;
    const vid = videoRef.current;
    if (!ga || !vid || !fullGameAudioUrl) return;

    ga.volume = 0.18; // Ducked background game SFX under Sarvam AI narration
    if (isOriginalAudioOn && isPlaying) {
      if (Math.abs(ga.currentTime - vid.currentTime) > 0.25) {
        ga.currentTime = vid.currentTime;
      }
      ga.play().catch(() => {});
    } else {
      ga.pause();
    }
  }, [isOriginalAudioOn, isPlaying, fullGameAudioUrl, videoRef]);

  const togglePlay = () => {
    const vid = videoRef.current;
    if (!vid) return;
    if (vid.paused) {
      vid.play().catch(() => {});
    } else {
      vid.pause();
    }
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      onTimeUpdate(time);
    }
    if (gameAudioRef.current) {
      gameAudioRef.current.currentTime = time;
    }
  };

  const toggleOriginalAudio = () => {
    const nextState = !isOriginalAudioOn;
    setIsOriginalAudioOn(nextState);
    if (gameAudioRef.current && videoRef.current && fullGameAudioUrl) {
      if (nextState && !videoRef.current.paused) {
        gameAudioRef.current.currentTime = videoRef.current.currentTime;
        gameAudioRef.current.volume = 0.18;
        gameAudioRef.current.play().catch(() => {});
      } else {
        gameAudioRef.current.pause();
      }
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
    if (!Number.isFinite(secs) || secs < 0) return "00:00";
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div
      ref={containerRef}
      className="w-full bg-black rounded-2xl overflow-hidden border border-studio-800 shadow-2xl relative flex flex-col group"
    >
      {/* Synced Original Game Audio Track (controlled by toggle button; OFF by default) */}
      {fullGameAudioUrl && <audio ref={gameAudioRef} src={fullGameAudioUrl} preload="auto" />}

      {/* Main Video Viewport (Single clean burned-in viral captions — ZERO double overlay) */}
      <div
        onClick={togglePlay}
        className="relative aspect-video w-full bg-studio-950 flex items-center justify-center overflow-hidden cursor-pointer"
      >
        <video
          ref={videoRef}
          src={fullVideoUrl}
          playsInline
          preload="metadata"
          className="w-full h-full object-contain"
          onTimeUpdate={() => {
            if (videoRef.current) {
              const t = videoRef.current.currentTime;
              onTimeUpdate(t);
              if (
                isOriginalAudioOn &&
                gameAudioRef.current &&
                Math.abs(gameAudioRef.current.currentTime - t) > 0.4
              ) {
                gameAudioRef.current.currentTime = t;
              }
            }
          }}
          onLoadedMetadata={() => {
            if (videoRef.current) {
              setDuration(videoRef.current.duration);
            }
          }}
          onWaiting={() => {
            setIsBuffering(true);
            gameAudioRef.current?.pause();
          }}
          onPlaying={() => {
            setIsBuffering(false);
            setIsPlaying(true);
          }}
          onCanPlay={() => setIsBuffering(false)}
          onPlay={() => setIsPlaying(true)}
          onPause={() => {
            setIsPlaying(false);
            gameAudioRef.current?.pause();
          }}
          onEnded={() => {
            setIsPlaying(false);
            gameAudioRef.current?.pause();
          }}
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

        {/* Buffering Indicator */}
        {isBuffering && (
          <div className="absolute z-20 p-3 rounded-full bg-black/70 text-white pointer-events-none">
            <Loader2 className="w-7 h-7 animate-spin text-[#FF4655]" />
          </div>
        )}

        {/* Center Play Button Overlay */}
        {!isPlaying && !isBuffering && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              togglePlay();
            }}
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
          value={Math.min(currentTime, duration || 100)}
          onChange={handleSeek}
          className="w-full h-1.5 bg-studio-800 rounded-lg appearance-none cursor-pointer accent-[#FF4655]"
        />

        {/* Controls Row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              type="button"
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
            {/* Dedicated Original Audio Toggle (OFF by default — Sarvam AI speaks by default) */}
            <button
              type="button"
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
            <button
              type="button"
              onClick={toggleFullscreen}
              className="text-slate-400 hover:text-white p-1"
            >
              <Maximize2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
