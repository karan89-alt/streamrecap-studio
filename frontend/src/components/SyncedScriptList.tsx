"use client";

import React, { useRef, useEffect, useState } from "react";
import { Edit3, Check, Save, FileText } from "lucide-react";
import { ScriptSegment } from "../types/recap";
import { updateScript } from "../lib/api";

interface SyncedScriptListProps {
  jobId: string;
  segments: ScriptSegment[];
  currentTime: number;
  onJumpToTime: (time: number) => void;
  onSegmentsUpdated?: (updated: ScriptSegment[]) => void;
}

export default function SyncedScriptList({
  jobId,
  segments: initialSegments,
  currentTime,
  onJumpToTime,
  onSegmentsUpdated,
}: SyncedScriptListProps) {
  const [segments, setSegments] = useState<ScriptSegment[]>(initialSegments);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const activeCardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSegments(initialSegments);
  }, [initialSegments]);

  const activeIndex = segments.findIndex(
    (s) => currentTime >= s.video_start && currentTime < s.video_end
  );

  // Scroll ONLY inside the script container without hijacking the main browser window scroll
  useEffect(() => {
    const container = containerRef.current;
    const card = activeCardRef.current;
    if (card && container && editingId === null && activeIndex >= 0) {
      const cardTop = card.offsetTop;
      const targetScroll = Math.max(0, cardTop - container.clientHeight / 3);
      container.scrollTo({
        top: targetScroll,
        behavior: "smooth",
      });
    }
  }, [activeIndex, editingId]);

  const startEdit = (seg: ScriptSegment, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(seg.id);
    setEditText(seg.dialogue_hindi);
  };

  const cancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
  };

  const saveEdit = (segId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = segments.map((s) =>
      s.id === segId ? { ...s, dialogue_hindi: editText.trim() } : s
    );
    setSegments(updated);
    setEditingId(null);
    if (onSegmentsUpdated) onSegmentsUpdated(updated);
  };

  const handlePersist = async () => {
    setIsSaving(true);
    try {
      await updateScript(jobId, segments);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (e) {
      console.error(e);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="w-full bg-studio-900 border border-studio-800 rounded-2xl p-4 shadow-2xl flex flex-col h-full max-h-[540px] lg:max-h-[600px]">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-studio-800">
        <div className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-[#FF4655]" />
          <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
            Hindi Script ({segments.length})
          </h3>
        </div>

        <button
          type="button"
          onClick={handlePersist}
          disabled={isSaving}
          className={`px-2.5 py-1 rounded-lg text-xs font-bold flex items-center gap-1 border transition ${
            saveSuccess
              ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
              : "bg-studio-800 text-slate-300 border-studio-700 hover:text-white"
          }`}
        >
          {saveSuccess ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
          <span>{saveSuccess ? "Saved" : isSaving ? "Saving..." : "Save"}</span>
        </button>
      </div>

      {/* Script List */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto space-y-2 pt-3 pr-1 relative"
      >
        {segments.map((seg, idx) => {
          const isActive = idx === activeIndex;
          const isEditing = editingId === seg.id;

          return (
            <div
              key={seg.id}
              ref={isActive ? activeCardRef : undefined}
              onClick={() => onJumpToTime(seg.video_start)}
              className={`p-3 rounded-xl border transition-all cursor-pointer relative ${
                isActive
                  ? "bg-studio-800 border-[#FF4655] shadow-lg shadow-[#FF4655]/10"
                  : "bg-studio-950/70 border-studio-800/80 hover:border-studio-700"
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1.5 text-xs">
                <span
                  className={`px-2 py-0.5 rounded font-mono font-bold text-[11px] ${
                    isActive ? "bg-[#FF4655] text-white" : "bg-studio-800 text-slate-400"
                  }`}
                >
                  {seg.video_start_fmt} - {seg.video_end_fmt}
                </span>

                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] text-amber-400/90 font-bold bg-amber-400/10 px-1.5 py-0.5 rounded">
                    {seg.act}
                  </span>
                  {!isEditing && (
                    <button
                      type="button"
                      onClick={(e) => startEdit(seg, e)}
                      className="p-1 text-slate-500 hover:text-white transition"
                      title="Edit dialogue"
                    >
                      <Edit3 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>

              {seg.scene_note && (
                <p className="text-[10px] text-slate-500 mb-1 truncate">
                  {seg.scene_note}
                </p>
              )}

              {isEditing ? (
                <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    rows={2}
                    className="w-full bg-studio-950 border border-[#FF4655] rounded-lg p-2 text-xs text-amber-200 focus:outline-none"
                  />
                  <div className="flex justify-end gap-1.5">
                    <button
                      type="button"
                      onClick={cancelEdit}
                      className="px-2 py-0.5 rounded bg-studio-800 text-slate-400 text-xs"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={(e) => saveEdit(seg.id, e)}
                      className="px-2.5 py-0.5 rounded bg-[#FF4655] text-white text-xs font-bold"
                    >
                      OK
                    </button>
                  </div>
                </div>
              ) : (
                <p
                  className={`text-xs sm:text-sm font-semibold leading-relaxed ${
                    isActive ? "text-amber-300 font-bold" : "text-slate-200"
                  }`}
                >
                  "{seg.dialogue_hindi}"
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
