"use client";

import { useState } from "react";
import type { TeamForm } from "@/lib/api";

const W = 640;
const H = 460;
const PAD = { top: 20, right: 20, bottom: 44, left: 52 };

// Attack vs defence, Opta style: xG for across, xG against down the y axis with better
// (lower) defence at the top, league-average guides splitting four quadrants.
export function TeamScatter({ teams }: { teams: TeamForm[] }) {
  const [hover, setHover] = useState<string | null>(null);
  const xs = teams.map((t) => t.xg_for);
  const ys = teams.map((t) => t.xg_against);
  const [x0, x1] = pad(Math.min(...xs), Math.max(...xs));
  const [y0, y1] = pad(Math.min(...ys), Math.max(...ys));
  const iw = W - PAD.left - PAD.right;
  const ih = H - PAD.top - PAD.bottom;
  const x = (v: number) => PAD.left + ((v - x0) / (x1 - x0)) * iw;
  const y = (v: number) => PAD.top + ((v - y0) / (y1 - y0)) * ih; // low xGA at top
  const mx = mean(xs);
  const my = mean(ys);
  const t = teams.find((d) => d.team === hover);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Team attack and defence">
        <rect x={x(mx)} y={PAD.top} width={W - PAD.right - x(mx)} height={y(my) - PAD.top} fill="#2a78d6" opacity="0.06" />
        <rect x={PAD.left} y={y(my)} width={x(mx) - PAD.left} height={PAD.top + ih - y(my)} fill="#e34948" opacity="0.06" />
        {ticksFor(x0, x1).map((v) => (
          <g key={`x${v}`}>
            <line x1={x(v)} x2={x(v)} y1={PAD.top} y2={PAD.top + ih} stroke="#eef2f6" />
            <text x={x(v)} y={H - 26} textAnchor="middle" className="fill-slate-500 text-[11px]">
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        {ticksFor(y0, y1).map((v) => (
          <g key={`y${v}`}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="#eef2f6" />
            <text x={PAD.left - 8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[11px]">
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        <line x1={x(mx)} x2={x(mx)} y1={PAD.top} y2={PAD.top + ih} stroke="#94a3b8" strokeDasharray="4 4" />
        <line x1={PAD.left} x2={W - PAD.right} y1={y(my)} y2={y(my)} stroke="#94a3b8" strokeDasharray="4 4" />
        <text x={W - PAD.right - 4} y={PAD.top + 14} textAnchor="end" className="fill-slate-500 text-[11px] font-semibold">
          Strong attack, tight defence
        </text>
        <text x={PAD.left + 4} y={PAD.top + ih - 6} className="fill-slate-500 text-[11px] font-semibold">
          Weak attack, leaky defence
        </text>
        <text x={PAD.left + iw / 2} y={H - 6} textAnchor="middle" className="fill-slate-700 text-[12px] font-medium">
          xG for per match →
        </text>
        <text
          transform={`translate(14 ${PAD.top + ih / 2}) rotate(-90)`}
          textAnchor="middle"
          className="fill-slate-700 text-[12px] font-medium"
        >
          ← xG against per match (lower is better)
        </text>
        {teams.map((d) => (
          <g key={d.team} onMouseEnter={() => setHover(d.team)} onMouseLeave={() => setHover(null)} className="cursor-default">
            <circle cx={x(d.xg_for)} cy={y(d.xg_against)} r="14" fill="transparent" />
            <circle
              cx={x(d.xg_for)}
              cy={y(d.xg_against)}
              r="6"
              fill="#2a78d6"
              stroke="#fff"
              strokeWidth="2"
              opacity={hover && hover !== d.team ? 0.4 : 1}
            />
            <text x={x(d.xg_for) + 9} y={y(d.xg_against)} dy="0.32em" className="fill-slate-800 text-[11px] font-semibold">
              {d.team}
            </text>
          </g>
        ))}
      </svg>
      {t && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-[130%] rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs text-white shadow-lg"
          style={{ left: `${(x(t.xg_for) / W) * 100}%`, top: `${(y(t.xg_against) / H) * 100}%` }}
        >
          <div className="font-semibold">{t.team}, last {t.matches}</div>
          <div className="tabular-nums text-slate-300">
            xG {t.xg_for.toFixed(2)} for, {t.xg_against.toFixed(2)} against
          </div>
          <div className="tabular-nums text-slate-300">
            Goals {t.goals_for.toFixed(1)} for, {t.goals_against.toFixed(1)} against
          </div>
        </div>
      )}
    </div>
  );
}

function mean(v: number[]): number {
  return v.reduce((a, b) => a + b, 0) / Math.max(v.length, 1);
}

function pad(lo: number, hi: number): [number, number] {
  const m = (hi - lo) * 0.12 || 0.2;
  return [Math.max(0, lo - m), hi + m];
}

function ticksFor(lo: number, hi: number): number[] {
  const step = (hi - lo) / 4 > 0.3 ? 0.5 : 0.25;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}
