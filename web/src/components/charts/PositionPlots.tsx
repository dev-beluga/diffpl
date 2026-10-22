"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { PlayerRow, Position } from "@/lib/api";

export type Metric = "xgi90" | "form" | "points" | "ownership";

export const METRICS: Record<Metric, { label: string; digits: number }> = {
  xgi90: { label: "xGI per 90", digits: 2 },
  form: { label: "Form (pts per match, last 4)", digits: 1 },
  points: { label: "Total points", digits: 0 },
  ownership: { label: "Ownership %", digits: 1 },
};

const POSITIONS: Position[] = ["GKP", "DEF", "MID", "FWD"];
const W = 300;
const H = 220;
const PAD = { top: 10, right: 10, bottom: 30, left: 38 };

// Small multiples, one panel per position: price across, the chosen metric up. Same scales in
// every panel so positions compare directly; labels only on each panel's top three.
export function PositionPlots({ players, metric }: { players: PlayerRow[]; metric: Metric }) {
  const router = useRouter();
  const [hover, setHover] = useState<number | null>(null);
  const xs = players.map((p) => p.price);
  const ys = players.map((p) => p[metric]);
  const x0 = Math.floor(Math.min(...xs, 4));
  const x1 = Math.ceil(Math.max(...xs, 8));
  const y1 = niceMax(Math.max(...ys, 0.1));
  const iw = W - PAD.left - PAD.right;
  const ih = H - PAD.top - PAD.bottom;
  const x = (v: number) => PAD.left + ((v - x0) / (x1 - x0)) * iw;
  const y = (v: number) => PAD.top + ih * (1 - v / y1);
  const fmt = (v: number) => v.toFixed(METRICS[metric].digits);

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {POSITIONS.map((pos) => {
        const group = players.filter((p) => p.position === pos);
        const top = new Set([...group].sort((a, b) => b[metric] - a[metric]).slice(0, 3).map((p) => p.element_id));
        const hov = group.find((p) => p.element_id === hover);
        return (
          <section key={pos} className="relative rounded-2xl bg-cream p-3 shadow-sm ring-1 ring-line">
            <div className="flex items-baseline justify-between">
              <h3 className="font-bold">{pos}</h3>
              <span className="text-xs text-muted">{group.length} players</span>
            </div>
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${pos}: price against ${METRICS[metric].label}`}>
              {[0, 0.5, 1].map((f) => (
                <g key={f}>
                  <line x1={PAD.left} x2={W - PAD.right} y1={y(y1 * f)} y2={y(y1 * f)} stroke="#e9dcc6" />
                  <text x={PAD.left - 5} y={y(y1 * f)} dy="0.32em" textAnchor="end" className="fill-[#8a7462] text-[10px]">
                    {fmt(y1 * f)}
                  </text>
                </g>
              ))}
              {range(x0, x1).map((v) => (
                <text key={v} x={x(v)} y={H - 14} textAnchor="middle" className="fill-[#8a7462] text-[10px]">
                  {v}
                </text>
              ))}
              <text x={PAD.left + iw / 2} y={H - 2} textAnchor="middle" className="fill-[#5e4a3c] text-[10px]">
                Price £m
              </text>
              {group.map((p) => (
                <g
                  key={p.element_id}
                  onMouseEnter={() => setHover(p.element_id)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => router.push(`/stats/players/${p.element_id}`)}
                  className="cursor-pointer"
                >
                  <circle cx={x(p.price)} cy={y(p[metric])} r="9" fill="transparent" />
                  <circle
                    cx={x(p.price)}
                    cy={y(p[metric])}
                    r={hover === p.element_id ? 6 : 4}
                    fill="#2a78d6"
                    stroke="#fffaf3"
                    strokeWidth="2"
                    opacity={hover && hover !== p.element_id ? 0.35 : 0.9}
                  />
                  {top.has(p.element_id) && (
                    <text x={x(p.price) + 6} y={y(p[metric]) - 5} className="fill-[#2a1d16] text-[10px] font-semibold">
                      {p.name}
                    </text>
                  )}
                </g>
              ))}
            </svg>
            {hov && (
              <div
                className="pointer-events-none absolute -translate-x-1/2 -translate-y-[120%] rounded-lg bg-espresso px-2.5 py-1.5 text-xs text-cream shadow-lg"
                style={{ left: `${(x(hov.price) / W) * 100}%`, top: `calc(${(y(hov[metric]) / H) * 100}% + 28px)` }}
              >
                <div className="font-semibold">
                  {hov.name} · {hov.team}
                </div>
                <div className="tabular-nums text-gold-soft">
                  £{hov.price.toFixed(1)}m · {METRICS[metric].label} {fmt(hov[metric])}
                </div>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function niceMax(v: number): number {
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

function range(a: number, b: number): number[] {
  const step = b - a > 8 ? 2 : 1;
  const out: number[] = [];
  for (let v = a; v <= b; v += step) out.push(v);
  return out;
}
