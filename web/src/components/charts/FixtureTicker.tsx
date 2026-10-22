"use client";

import { useMemo, useState } from "react";
import type { TickerCell, TickerRow } from "@/lib/api";

type Mode = "attack" | "defence";

// Diverging blue (good) <-> red (bad) around a neutral grey, three steps per arm. Adjacent
// steps pass the CVD check; every cell also prints opponent and value, so colour is never the
// only encoding.
const GOOD = ["#9ec5f4", "#3987e5", "#1c5cab"];
const BAD = ["#f2a9a8", "#e34948", "#b92f2f"];
const NEUTRAL = "#f0efec";

export function FixtureTicker({ rows }: { rows: TickerRow[] }) {
  const [mode, setMode] = useState<Mode>("attack");
  const gws = useMemo(
    () => Array.from(new Set(rows.flatMap((r) => r.fixtures.map((f) => f.gw)))).sort((a, b) => a - b),
    [rows],
  );
  const value = (f: TickerCell) => (mode === "attack" ? f.xg_for : -f.xg_against);
  const all = rows.flatMap((r) => r.fixtures.map(value));
  const mid = all.reduce((a, b) => a + b, 0) / Math.max(all.length, 1);
  const spread = Math.max(...all.map((v) => Math.abs(v - mid)), 0.01);
  const total = (r: TickerRow) => r.fixtures.reduce((s, f) => s + value(f), 0);
  const sorted = [...rows].sort((a, b) => total(b) - total(a));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-xl bg-slate-100 p-1 text-sm">
          {(["attack", "defence"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded-lg px-3 py-1.5 font-medium capitalize ${mode === m ? "bg-white shadow-sm" : "text-slate-600"}`}
            >
              {m === "attack" ? "For attackers" : "For defenders"}
            </button>
          ))}
        </div>
        <Legend mode={mode} />
      </div>
      <div className="overflow-x-auto rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
        <table className="w-full border-separate border-spacing-[2px] text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wider text-slate-500">
              <th className="px-3 py-2 text-left">Team</th>
              {gws.map((g) => (
                <th key={g} className="px-2 py-2">
                  GW{g}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.team}>
                <td className="px-3 py-1.5 font-semibold">{r.team}</td>
                {gws.map((g) => {
                  const fs = r.fixtures.filter((f) => f.gw === g);
                  if (!fs.length)
                    return (
                      <td key={g} className="rounded-md bg-slate-50 px-2 py-1.5 text-center text-xs text-slate-400">
                        Blank
                      </td>
                    );
                  return (
                    <td key={g} className="p-0">
                      <div className="flex gap-[2px]">
                        {fs.map((f, i) => {
                          const t = (value(f) - mid) / spread; // -1 .. 1
                          const step = Math.min(2, Math.floor(Math.abs(t) * 3));
                          const bg = Math.abs(t) < 0.12 ? NEUTRAL : t > 0 ? GOOD[step] : BAD[step];
                          const dark = step >= 1 && Math.abs(t) >= 0.12;
                          return (
                            <div
                              key={i}
                              title={`${r.team} ${f.home ? "vs" : "at"} ${f.opponent}: ${f.xg_for.toFixed(2)} xG for, ${f.xg_against.toFixed(2)} against`}
                              className={`min-w-[64px] flex-1 rounded-md px-2 py-1.5 text-center ${dark ? "text-white" : "text-slate-900"}`}
                              style={{ background: bg }}
                            >
                              <div className="font-semibold">
                                {f.opponent} <span className="font-normal opacity-80">({f.home ? "H" : "A"})</span>
                              </div>
                              <div className="text-[11px] tabular-nums opacity-80">
                                {(mode === "attack" ? f.xg_for : f.xg_against).toFixed(2)}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Legend({ mode }: { mode: Mode }) {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-600">
      <span>{mode === "attack" ? "Fewer expected goals" : "More goals expected against"}</span>
      {[...BAD].reverse().map((c) => (
        <span key={c} className="h-3 w-5 rounded-sm" style={{ background: c }} />
      ))}
      <span className="h-3 w-5 rounded-sm" style={{ background: NEUTRAL }} />
      {GOOD.map((c) => (
        <span key={c} className="h-3 w-5 rounded-sm" style={{ background: c }} />
      ))}
      <span>{mode === "attack" ? "More expected goals" : "Fewer goals expected against"}</span>
    </div>
  );
}
