"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { METRICS, type Metric, PositionPlots } from "@/components/charts/PositionPlots";
import { Failed, Spinner } from "@/components/States";
import type { PlayerRow, Position } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Key = keyof Pick<PlayerRow, "price" | "ownership" | "minutes" | "points" | "form" | "xg90" | "xa90" | "xgi90">;

const COLUMNS: { key: Key; label: string; title: string; digits: number }[] = [
  { key: "price", label: "£m", title: "Price", digits: 1 },
  { key: "ownership", label: "Own %", title: "Selected by, percent of managers", digits: 1 },
  { key: "minutes", label: "Mins", title: "Minutes played", digits: 0 },
  { key: "points", label: "Pts", title: "Total points", digits: 0 },
  { key: "form", label: "Form", title: "Points per match, last 4 matches", digits: 1 },
  { key: "xg90", label: "xG/90", title: "Expected goals per 90 minutes", digits: 2 },
  { key: "xa90", label: "xA/90", title: "Expected assists per 90 minutes", digits: 2 },
  { key: "xgi90", label: "xGI/90", title: "Expected goal involvements per 90", digits: 2 },
];
const POSITIONS: (Position | "ALL")[] = ["ALL", "GKP", "DEF", "MID", "FWD"];
const MIN_MINUTES = [0, 90, 270, 450];

export default function PlayersPage() {
  const res = useApi<PlayerRow[]>("/api/stats/players");
  const [pos, setPos] = useState<Position | "ALL">("ALL");
  const [query, setQuery] = useState("");
  const [minMins, setMinMins] = useState(270);
  const [sort, setSort] = useState<{ key: Key; desc: boolean }>({ key: "points", desc: true });
  const [metric, setMetric] = useState<Metric>("xgi90");

  const rows = useMemo(() => {
    if (res.status !== "ok") return [];
    const q = query.trim().toLowerCase();
    return res.data
      .filter((r) => (pos === "ALL" || r.position === pos) && r.minutes >= minMins)
      .filter((r) => !q || r.name.toLowerCase().includes(q) || r.team.toLowerCase().includes(q))
      .sort((a, b) => (sort.desc ? b[sort.key] - a[sort.key] : a[sort.key] - b[sort.key]));
  }, [res, pos, query, minMins, sort]);

  if (res.status === "loading") return <Spinner label="Loading players" />;
  if (res.status === "error") return <Failed message={res.message} />;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search player or club"
          className="w-56 rounded-xl border border-line bg-cream px-3 py-2 text-sm shadow-sm outline-none focus:border-gold"
          aria-label="Search"
        />
        <div className="inline-flex rounded-xl bg-sand-deep p-1 text-sm" role="group" aria-label="Position">
          {POSITIONS.map((p) => (
            <button
              key={p}
              onClick={() => setPos(p)}
              className={`rounded-lg px-3 py-1.5 font-medium ${pos === p ? "bg-cream shadow-sm" : "text-ink-soft"}`}
            >
              {p === "ALL" ? "All" : p}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-soft">
          Min. minutes
          <select
            value={minMins}
            onChange={(e) => setMinMins(Number(e.target.value))}
            className="rounded-lg border border-line bg-cream px-2 py-1.5"
          >
            {MIN_MINUTES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <span className="ml-auto text-xs text-muted">{rows.length} players</span>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold">Plot</span>
        {(Object.keys(METRICS) as Metric[]).map((m) => (
          <button
            key={m}
            onClick={() => setMetric(m)}
            className={`rounded-lg px-3 py-1.5 ${metric === m ? "bg-espresso text-cream" : "bg-sand-deep text-ink-soft"}`}
          >
            {METRICS[m].label}
          </button>
        ))}
        <span className="text-xs text-muted">against price, by position. Click a dot for the player.</span>
      </div>
      <PositionPlots players={rows} metric={metric} />
      <div className="overflow-x-auto rounded-2xl bg-cream shadow-sm ring-1 ring-line">
        <table className="w-full text-sm">
          <thead className="bg-sand text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2.5 text-left">Player</th>
              {COLUMNS.map((c) => (
                <th key={c.key} className="px-3 py-2.5 text-right" title={c.title}>
                  <button
                    onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : true }))}
                    className={`uppercase ${sort.key === c.key ? "text-ink" : ""}`}
                  >
                    {c.label}
                    {sort.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.slice(0, 200).map((r) => (
              <tr key={r.element_id} className="hover:bg-sand">
                <td className="px-3 py-2">
                  <Link href={`/stats/players/${r.element_id}`} className="font-semibold hover:text-gold-deep">
                    {r.name}
                  </Link>
                  <span className="ml-2 text-xs text-muted">
                    {r.team} · {r.position}
                  </span>
                </td>
                {COLUMNS.map((c) => (
                  <td key={c.key} className={`px-3 py-2 text-right tabular-nums ${sort.key === c.key ? "font-semibold" : ""}`}>
                    {r[c.key].toFixed(c.digits)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
