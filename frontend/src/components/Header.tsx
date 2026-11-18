"use client";

import React, { useEffect, useState } from "react";
import { Video, Tv } from "lucide-react";
import { checkBackendHealth } from "../lib/api";

export default function Header() {
  const [status, setStatus] = useState<"checking" | "healthy" | "offline">("checking");

  useEffect(() => {
    let active = true;
    const pollHealth = async () => {
      const res = await checkBackendHealth();
      if (!active) return;
      setStatus(res?.status === "healthy" ? "healthy" : "offline");
    };
    pollHealth();
    const timer = setInterval(pollHealth, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
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

          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border font-bold ${
              status === "healthy"
                ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-400"
                : status === "offline"
                ? "bg-rose-950/40 border-rose-500/30 text-rose-400"
                : "bg-amber-950/40 border-amber-500/30 text-amber-400"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                status === "healthy"
                  ? "bg-emerald-400 animate-pulse"
                  : status === "offline"
                  ? "bg-rose-400"
                  : "bg-amber-400 animate-ping"
              }`}
            />
            <span>
              {status === "healthy"
                ? "Cloud Ready"
                : status === "offline"
                ? "Reconnecting..."
                : "Checking..."}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}
