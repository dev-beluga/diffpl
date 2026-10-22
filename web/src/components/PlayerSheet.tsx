"use client";

import Link from "next/link";
import { useEffect } from "react";
import { PlayerDetailView } from "./PlayerDetailView";

// Slide-over panel with a player's profile, opened by tapping a card on the pitch.
export function PlayerSheet({ id, onClose }: { id: number | null; onClose: () => void }) {
  useEffect(() => {
    if (id == null) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [id, onClose]);

  if (id == null) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Player profile">
      <button className="absolute inset-0 bg-espresso/50" onClick={onClose} aria-label="Close" />
      <div className="relative h-full w-full max-w-xl overflow-y-auto bg-sand p-4 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <Link href={`/stats/players/${id}`} className="text-sm font-medium text-gold-deep hover:underline">
            Open full page
          </Link>
          <button onClick={onClose} className="rounded-lg px-3 py-1.5 text-sm font-semibold text-ink-soft hover:bg-sand-deep">
            Close ✕
          </button>
        </div>
        <PlayerDetailView id={id} compact />
      </div>
    </div>
  );
}
