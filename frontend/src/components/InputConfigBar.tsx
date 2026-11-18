"use client";

import React, { useState } from "react";
import { Youtube, Sparkles, Clock, ArrowRight, Wand2, Mic, Gauge } from "lucide-react";

interface InputConfigBarProps {
  onGenerate: (
    url: string,
    targetMinutes: number,
    storyStyle: string,
    voiceSpeaker: string,
    playbackSpeed: number
  ) => void;
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

const SPEEDS = [
  { value: 1.0, label: "1x" },
  { value: 1.25, label: "1.25x" },
  { value: 1.5, label: "1.5x" },
  { value: 1.75, label: "1.75x" },
  { value: 2.0, label: "2x" },
];

const STYLES = [
  "Funny Storytelling",
  "Facts Storytelling",
  "Documentary Storytelling",
  "Mystery & Suspense Storytelling",
  "Investigative Storytelling",
  "Cinematic Storytelling",
  "Chronological Storytelling",
  "Case Study Storytelling",
  "Explainer Storytelling",
];

const MALE_VOICES = [
  { id: "shubh", label: "Shubh (Energetic)" },
  { id: "kabir", label: "Kabir (Deep Cinematic)" },
  { id: "aditya", label: "Aditya (Storyteller)" },
  { id: "rahul", label: "Rahul (Funny / Roast)" },
  { id: "rohan", label: "Rohan (Fast Action)" },
  { id: "amit", label: "Amit (Documentary)" },
  { id: "dev", label: "Dev (Suspense)" },
  { id: "mohit", label: "Mohit (Gaming)" },
];

const FEMALE_VOICES = [
  { id: "ritu", label: "Ritu (Expressive)" },
  { id: "priya", label: "Priya (Storyteller)" },
  { id: "neha", label: "Neha (Energetic)" },
  { id: "kavya", label: "Kavya (Dramatic)" },
  { id: "shreya", label: "Shreya (Explainer)" },
  { id: "shruti", label: "Shruti (Documentary)" },
];

const REAL_DEMO_URL = "https://www.youtube.com/watch?v=RbVGCHFf0ZY";

export default function InputConfigBar({ onGenerate, isProcessing }: InputConfigBarProps) {
  const [url, setUrl] = useState(REAL_DEMO_URL);
  const [targetMinutes, setTargetMinutes] = useState(5);
  const [playbackSpeed, setPlaybackSpeed] = useState(1.0);
  const [storyStyle, setStoryStyle] = useState("Funny Storytelling");
  const [voiceGender, setVoiceGender] = useState<"male" | "female">("male");
  const [voiceSpeaker, setVoiceSpeaker] = useState("shubh");

  const activeVoices = voiceGender === "male" ? MALE_VOICES : FEMALE_VOICES;

  const handleGenderChange = (g: "male" | "female") => {
    setVoiceGender(g);
    setVoiceSpeaker(g === "male" ? MALE_VOICES[0].id : FEMALE_VOICES[0].id);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    onGenerate(url.trim(), targetMinutes, storyStyle, voiceSpeaker, playbackSpeed);
  };

  return (
    <div className="w-full bg-studio-900 border border-studio-800 rounded-2xl p-5 shadow-2xl">
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* URL Input */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Youtube className="w-4 h-4 text-[#FF4655]" />
              YouTube Stream / VOD URL
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
            placeholder="Paste YouTube stream or VOD URL..."
            className="w-full h-11 bg-studio-950 border border-studio-700 focus:border-[#FF4655] rounded-xl px-4 text-sm text-slate-100 placeholder-slate-500 focus:outline-none transition"
            disabled={isProcessing}
          />
        </div>

        {/* Row 1: Duration + Render Speed */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* 1. Video Duration */}
          <div className="lg:col-span-7 space-y-2">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-amber-400" />
              1. Video Duration
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
                    className={`py-2 px-2 rounded-xl text-xs font-bold transition text-center border ${
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

          {/* 2. Video & Voice Speed */}
          <div className="lg:col-span-5 space-y-2">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Gauge className="w-3.5 h-3.5 text-cyan-400" />
              2. Video & Voice Speed
            </label>
            <div className="grid grid-cols-5 gap-2">
              {SPEEDS.map((sp) => {
                const isSelected = playbackSpeed === sp.value;
                return (
                  <button
                    key={sp.value}
                    type="button"
                    onClick={() => setPlaybackSpeed(sp.value)}
                    disabled={isProcessing}
                    className={`py-2 px-2 rounded-xl text-xs font-bold transition text-center border font-mono ${
                      isSelected
                        ? "bg-cyan-500 text-black border-cyan-400 shadow-lg shadow-cyan-500/20"
                        : "bg-studio-950 border-studio-800 hover:border-studio-700 text-slate-300"
                    }`}
                  >
                    {sp.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* 3. Storytelling Style (Funny & Facts separated!) */}
        <div className="space-y-2">
          <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-[#FF4655]" />
            3. Storytelling Style
          </label>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
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

        {/* 4. Sarvam AI Indian Voice + Generate CTA */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 pt-1 items-end">
          <div className="lg:col-span-7 space-y-2">
            <label className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
              <Mic className="w-3.5 h-3.5 text-purple-400" />
              4. Sarvam AI Indian Voice
            </label>
            <div className="grid grid-cols-12 gap-2">
              <button
                type="button"
                onClick={() => handleGenderChange("male")}
                disabled={isProcessing}
                className={`col-span-3 py-2.5 px-2 rounded-xl border text-xs font-bold transition ${
                  voiceGender === "male"
                    ? "bg-purple-600 text-white border-purple-500"
                    : "bg-studio-950 border-studio-800 text-slate-300 hover:border-studio-700"
                }`}
              >
                Male
              </button>
              <button
                type="button"
                onClick={() => handleGenderChange("female")}
                disabled={isProcessing}
                className={`col-span-3 py-2.5 px-2 rounded-xl border text-xs font-bold transition ${
                  voiceGender === "female"
                    ? "bg-purple-600 text-white border-purple-500"
                    : "bg-studio-950 border-studio-800 text-slate-300 hover:border-studio-700"
                }`}
              >
                Female
              </button>
              <select
                value={voiceSpeaker}
                onChange={(e) => setVoiceSpeaker(e.target.value)}
                disabled={isProcessing}
                className="col-span-6 h-10 bg-studio-950 border border-studio-700 focus:border-purple-500 rounded-xl px-3 text-xs font-bold text-slate-100 focus:outline-none"
              >
                {activeVoices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="lg:col-span-5">
            <button
              type="submit"
              disabled={isProcessing}
              className={`w-full h-10 px-6 rounded-xl font-bold text-sm tracking-wide flex items-center justify-center gap-2 transition ${
                isProcessing
                  ? "bg-studio-800 text-slate-500 cursor-not-allowed"
                  : "bg-gradient-to-r from-[#FF4655] to-[#FF2D55] hover:brightness-110 text-white shadow-lg shadow-[#FF4655]/25 active:scale-95"
              }`}
            >
              {isProcessing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  <span>Rendering {playbackSpeed}x HD...</span>
                </>
              ) : (
                <>
                  <Wand2 className="w-4 h-4" />
                  <span>Generate {playbackSpeed}x Full HD Video</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
