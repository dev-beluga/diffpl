"use client";

import { useState } from "react";

export interface Bar {
  label: string; // x tick, e.g. "GW3"
  value: number;
  tip: string; // tooltip line under the value
}

const W = 640;
const PAD = { top: 12, right: 8, bottom: 26, left: 34 };

// Single-series bar chart: one hue, rounded data-ends on the baseline, hover tooltip.
export function Bars({
  bars,
  height = 200,
  color = "#2a78d6",
  format = (v: number) => v.toFixed(1),
  ticks = 4,
}: {
  bars: Bar[];
  height?: number;
  color?: string;
  format?: (v: number) => string;
  ticks?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...bars.map((b) => b.value), 0) || 1;
  const min = Math.min(...bars.map((b) => b.value), 0);
  const span = max - min || 1;
  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const y = (v: number) => PAD.top + innerH * (1 - (v - min) / span);
  const band = innerW / Math.max(bars.length, 1);
  const bw = Math.min(28, band * 0.7);
  const step = niceStep(span / ticks);
  const gridValues: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) gridValues.push(v);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="w-full" role="img" aria-label="Bar chart">
        {gridValues.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="#e2e8f0" strokeWidth={v === 0 ? 1.5 : 1} />
            <text x={PAD.left - 6} y={y(v)} dy="0.32em" textAnchor="end" className="fill-slate-500 text-[10px]">
              {format(v)}
            </text>
          </g>
        ))}
        {bars.map((b, i) => {
          const cx = PAD.left + band * i + band / 2;
          const top = y(Math.max(b.value, 0));
          const bottom = y(Math.min(b.value, 0));
          const h = Math.max(bottom - top, 0.5);
          const r = Math.min(4, h / 2, bw / 2);
          const up = b.value >= 0;
          // Round only the end away from the baseline.
          const d = up
            ? `M${cx - bw / 2},${bottom} V${top + r} Q${cx - bw / 2},${top} ${cx - bw / 2 + r},${top} H${cx + bw / 2 - r} Q${cx + bw / 2},${top} ${cx + bw / 2},${top + r} V${bottom} Z`
            : `M${cx - bw / 2},${top} V${bottom - r} Q${cx - bw / 2},${bottom} ${cx - bw / 2 + r},${bottom} H${cx + bw / 2 - r} Q${cx + bw / 2},${bottom} ${cx + bw / 2},${bottom - r} V${top} Z`;
          return (
            <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={cx - band / 2} y={PAD.top} width={band} height={innerH} fill="transparent" />
              <path d={d} fill={color} opacity={hover === null || hover === i ? 1 : 0.45} />
              {(bars.length <= 20 || i % Math.ceil(bars.length / 20) === 0) && (
                <text x={cx} y={height - 8} textAnchor="middle" className="fill-slate-500 text-[10px]">
                  {b.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-lg bg-espresso px-2.5 py-1.5 text-xs text-white shadow-lg"
          style={{
            left: `${((PAD.left + band * hover + band / 2) / W) * 100}%`,
            top: `${(y(Math.max(bars[hover].value, 0)) / height) * 100}%`,
          }}
        >
          <div className="font-semibold tabular-nums">{format(bars[hover].value)}</div>
          <div className="text-gold-soft">{bars[hover].tip}</div>
        </div>
      )}
    </div>
  );
}

function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw || 1));
  const n = raw / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}
