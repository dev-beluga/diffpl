"use client";

import { FixtureTicker } from "@/components/charts/FixtureTicker";
import { Failed, Spinner } from "@/components/States";
import type { TickerRow } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function FixturesPage() {
  const res = useApi<TickerRow[]>("/api/stats/fixtures");
  if (res.status === "loading") return <Spinner label="Loading fixtures" />;
  if (res.status === "error") return <Failed message={res.message} />;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-slate-600">
        Expected goals per fixture for the next 6 GWs: league average × the team&apos;s attack × the opponent&apos;s
        defence, from xG over the last 6 matches pulled toward average. Teams with the best run come first.
      </p>
      <FixtureTicker rows={res.data} />
    </div>
  );
}
