"use client";

import React, { useState } from "react";
import { Youtube, Sparkles, Clock, ArrowRight, Wand2 } from "lucide-react";

interface InputConfigBarProps {
  onGenerate: (url: string, targetMinutes: number, storyStyle: string) => void;
  isProcessing: boolean;
}

const LENGTHS = [
  { value: 5, label: "5 Min" },
  { value: 10, label: "10 Min" },
  { value: 15, label: "15 Min" },
  { value: 20, label: "20 Min" },
  { value: 25, label: "25 Min" },
  { value: 30, label: "30 Min" },
];

const STYLES = [
  "Funny + Facts",
  "Documentary Storytelling",
  "Mystery & Suspense Storytelling",
  "Investigative Storytelling",
  "Cinematic Storytelling",
  "Chronological Storytelling",
  "Case Study Storytelling",
  "Explainer Storytelling",
];

const REAL_DEMO_URL = "https://www.youtube.com/watch?v=RbVGCHFf0ZY";

export default function InputConfigBar({ onGenerate, isProcessing }: InputConfigBarProps) {
  const [url, setUrl] = useState(REAL_DEMO_URL);
  const [targetMinutes, setTargetMinutes] = useState(15);
  const [storyStyle, setStoryStyle] = useState("Explainer Storytelling");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    onGenerate(url.trim(), targetMinutes, storyStyle);
  };

  return (
    <div className="w-full bg-studio-900 border border-studio-800 rounded-2xl p-5 shadow-2xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* URL Input */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Youtube className="w-4 h-4 text-[#FF4655]" />
              YouTube Gaming Stream / VOD URL
            </label>
            <button
              type="button"
              onClick={() => setUrl(REAL_DEMO_URL)}
              className="text-[11px] text-[#FF4655] hover:underline font-semibold"
            >
              Use GTA V Demo
            </button>
          </div>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste YouTube stream or past live stream URL..."
            className="w-full h-11 bg-studio-950 border border-studio-700 focus:border-[#FF4655] rounded-xl px-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none transition"
            disabled={isProcessing}
          />
        </div>

        {/* 1. Video Duration Selection */}
        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-brand-yellow" />
            1. Select Video Duration
          </label>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {LENGTHS.map((item) => {
              const isSelected = targetMinutes === item.value;
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setTargetMinutes(item.value)}
                  disabled={isProcessing}
                  className={`py-2 px-3 rounded-xl text-xs font-bold transition text-center border ${
                    isSelected
                      ? "bg-[#FF4655] text-white border-[#FF4655] shadow-lg shadow-[#FF4655]/20"
                      : "bg-studio-950 border-studio-800 hover:border-studio-700 text-slate-300"
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* 2. Storytelling Style Selection */}
        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-[#FF4655]" />
            2. Select Storytelling Style
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {STYLES.map((style) => {
              const isSelected = storyStyle === style;
              return (
                <button
                  key={style}
                  type="button"
                  onClick={() => setStoryStyle(style)}
                  disabled={isProcessing}
                  className={`p-2.5 rounded-xl border text-left text-xs font-bold transition truncate ${
                    isSelected
                      ? "bg-studio-800 text-amber-300 border-amber-400/80 ring-1 ring-amber-400/50 shadow-md"
                      : "bg-studio-950 border-studio-800 hover:border-studio-700 text-slate-300"
                  }`}
                >
                  {style}
                </button>
              );
            })}
          </div>
        </div>

        {/* CTA Button */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={isProcessing}
            className={`w-full py-3 px-6 rounded-xl font-bold text-sm tracking-wide flex items-center justify-center gap-2 transition ${
              isProcessing
                ? "bg-studio-800 text-slate-500 cursor-not-allowed"
                : "bg-gradient-to-r from-[#FF4655] to-[#FF2D55] hover:brightness-110 text-white shadow-lg shadow-[#FF4655]/25 active:scale-95"
            }`}
          >
            {isProcessing ? (
              <>
                <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                <span>Processing Full HD Recap Video...</span>
              </>
            ) : (
              <>
                <Wand2 className="w-4 h-4" />
                <span>Generate Full HD Recap Video</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
