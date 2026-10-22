"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Bars } from "@/components/charts/Bars";
import { Shirt } from "@/components/Shirt";
import { Failed, Spinner } from "@/components/States";
import type { PlayerDetail } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function PlayerPage() {
  const { id } = useParams<{ id: string }>();
  const res = useApi<PlayerDetail>(`/api/stats/players/${id}`);
  if (res.status === "loading") return <Spinner label="Loading player. The first visit runs the projection model." />;
  if (res.status === "error") return <Failed message={res.message} />;
  const { row, matches, points_bins, points_probs } = res.data;
  const fixture = (m: (typeof matches)[number]) => `GW${m.gw} ${m.home ? "vs" : "at"} ${m.opponent}, ${m.minutes} min`;
  const expected = points_bins.reduce((s, v, i) => s + v * (points_probs[i] ?? 0), 0);
  const pBlank = points_probs[points_bins.indexOf(0)] ?? 0;
  const pHaul = points_bins.reduce((s, v, i) => s + (v >= 10 ? points_probs[i] : 0), 0);

  return (
    <div className="flex flex-col gap-5">
      <Link href="/stats/players" className="text-sm text-slate-500 hover:text-slate-800">
        ← All players
      </Link>
      <section className="flex items-center gap-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <Shirt team={row.team} goalkeeper={row.position === "GKP"} size={72} />
        <div className="flex-1">
          <h2 className="text-2xl font-black tracking-tight">{row.name}</h2>
          <div className="text-sm text-slate-500">
            {row.team} · {row.position} · £{row.price.toFixed(1)}m · {row.ownership.toFixed(1)}% owned
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4 text-right sm:grid-cols-5">
          <Kpi label="Points" value={row.points.toFixed(0)} />
          <Kpi label="Form" value={row.form.toFixed(1)} />
          <Kpi label="xG/90" value={row.xg90.toFixed(2)} />
          <Kpi label="xA/90" value={row.xa90.toFixed(2)} className="hidden sm:block" />
          <Kpi label="Mins" value={row.minutes.toFixed(0)} className="hidden sm:block" />
        </div>
      </section>

      {points_probs.length > 0 && (
        <Card
          title="Next GW points distribution"
          note={`Champion model. Expected ${expected.toFixed(1)} points; P(blank) ${(pBlank * 100).toFixed(0)}%, P(10+) ${(pHaul * 100).toFixed(0)}%.`}
        >
          <Bars
            bars={points_bins.map((v, i) => ({
              label: i === points_bins.length - 1 ? `${v}+` : String(v),
              value: points_probs[i] * 100,
              tip: `${i === points_bins.length - 1 ? `${v} or more` : v} points`,
            }))}
            format={(v) => `${v.toFixed(0)}%`}
            color="#1c5cab"
          />
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Points per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.points, tip: fixture(m) }))} format={(v) => v.toFixed(0)} />
        </Card>
        <Card title="Minutes per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.minutes, tip: fixture(m) }))} format={(v) => v.toFixed(0)} color="#52514e" />
        </Card>
        <Card title="Expected goals (xG) per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.xg, tip: fixture(m) }))} format={(v) => v.toFixed(2)} />
        </Card>
        <Card title="Expected assists (xA) per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.xa, tip: fixture(m) }))} format={(v) => v.toFixed(2)} />
        </Card>
      </div>
    </div>
  );
}

function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <h3 className="font-bold">{title}</h3>
      {note && <p className="mb-2 text-sm text-slate-500">{note}</p>}
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Kpi({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return (
    <div className={className}>
      <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-xl font-bold tabular-nums">{value}</div>
    </div>
  );
}
