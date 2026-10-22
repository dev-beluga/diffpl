"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { PlayerDetailView } from "@/components/PlayerDetailView";

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="flex flex-col gap-4">
      <Link href="/stats/players" className="text-sm text-muted hover:text-ink">
        ← All players
      </Link>
      <PlayerDetailView id={Number(id)} />
    </div>
  );
}
