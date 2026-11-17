"use client";

import React, { useEffect, useState } from "react";
import { Video, Tv, CheckCircle2 } from "lucide-react";
import { checkBackendHealth } from "../lib/api";

export default function Header() {
  const [backendStatus, setBackendStatus] = useState<{ status: string; ffmpeg_detected?: boolean }>({
    status: "online",
  });

  useEffect(() => {
    checkBackendHealth().then((res) => {
      setBackendStatus(res);
    });
  }, []);

  return (
    <header className="w-full border-b border-studio-800 bg-studio-950/90 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#FF4655] flex items-center justify-center text-white shadow-md shadow-[#FF4655]/20">
            <Video className="w-4 h-4" />
          </div>
          <span className="font-extrabold text-base tracking-tight text-white">
            StreamRecap Studio
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-studio-900 border border-studio-800 text-slate-300">
            <Tv className="w-3.5 h-3.5 text-[#FF4655]" />
            <span className="font-bold">1080p Full HD</span>
          </div>

          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/40 border border-emerald-500/30 text-emerald-400 font-bold">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>Engine Ready</span>
          </div>
        </div>
      </div>
    </header>
  );
}
