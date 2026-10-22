"use client";

import { Bars } from "@/components/charts/Bars";
import { Shirt } from "@/components/Shirt";
import { Failed, Spinner } from "@/components/States";
import type { MatchRow, PlayerDetail, TickerRow } from "@/lib/api";
import { useApi } from "@/lib/useApi";

// Player profile: what FPL shows (price, ownership, history) plus what it does not: the
// champion's next-GW points distribution, P(60+ minutes), expected points over the next GWs
// and an xG-based fixture run.
export function PlayerDetailView({ id, compact = false }: { id: number; compact?: boolean }) {
  const res = useApi<PlayerDetail>(`/api/stats/players/${id}`);
  const ticker = useApi<TickerRow[]>("/api/stats/fixtures");
  if (res.status === "loading") return <Spinner label="Loading player. The first visit runs the projection model." />;
  if (res.status === "error") return <Failed message={res.message} />;
  const { row, matches, points_bins, points_probs, p60, xp_horizon, horizon } = res.data;
  const expected = points_bins.reduce((s, v, i) => s + v * (points_probs[i] ?? 0), 0);
  const pBlank = points_bins.reduce((s, v, i) => s + (v <= 2 ? points_probs[i] : 0), 0);
  const pHaul = points_bins.reduce((s, v, i) => s + (v >= 10 ? points_probs[i] : 0), 0);
  const run = ticker.status === "ok" ? ticker.data.find((t) => t.team === row.team)?.fixtures ?? [] : [];
  const label = (m: MatchRow) => `GW${m.gw} ${m.home ? "vs" : "at"} ${m.opponent}, ${m.minutes} min`;

  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-wrap items-center gap-4 rounded-2xl bg-espresso p-5 text-cream shadow-sm">
        <Shirt team={row.team} goalkeeper={row.position === "GKP"} size={72} />
        <div className="min-w-[160px] flex-1">
          <div className="text-xs font-semibold uppercase tracking-wider text-gold">
            {row.position} · {row.team}
          </div>
          <h2 className="text-2xl font-black tracking-tight">{row.name}</h2>
          <div className="text-sm text-sand-deep">
            £{row.price.toFixed(1)}m · {row.ownership.toFixed(1)}% owned
          </div>
        </div>
        <div className="grid grid-cols-3 gap-x-5 gap-y-2 text-right">
          <Kpi label="Points" value={row.points.toFixed(0)} />
          <Kpi label="Form" value={row.form.toFixed(1)} />
          <Kpi label="xGI/90" value={row.xgi90.toFixed(2)} />
        </div>
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="xP next GW" value={expected.toFixed(1)} note="Mean of the distribution below" />
        <Stat label={`xP next ${horizon} GWs`} value={xp_horizon.toFixed(1)} note="Champion model, fixture-adjusted" />
        <Stat label="P(60+ mins)" value={p60 == null ? "n/a" : `${Math.round(p60 * 100)}%`} note="Minutes model" />
        <Stat label="P(haul, 10+)" value={`${Math.round(pHaul * 100)}%`} note={`P(2 or fewer) ${Math.round(pBlank * 100)}%`} />
      </section>

      {run.length > 0 && (
        <Card title="Fixture run" note="Expected goals for and against the team, from recent xG.">
          <div className="flex flex-wrap gap-2">
            {run.map((f, i) => (
              <div key={i} className="min-w-[88px] rounded-xl bg-sand px-3 py-2 text-center ring-1 ring-line">
                <div className="text-[11px] font-semibold text-muted">GW{f.gw}</div>
                <div className="font-bold">
                  {f.opponent} <span className="font-normal text-muted">({f.home ? "H" : "A"})</span>
                </div>
                <div className="text-[11px] tabular-nums text-ink-soft">
                  {f.xg_for.toFixed(2)} for · {f.xg_against.toFixed(2)} vs
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {points_probs.length > 0 && (
        <Card title="Next GW points distribution" note="Chance of each score from the champion model; FPL shows only a single number.">
          <Bars
            bars={points_bins.map((v, i) => ({
              label: i === points_bins.length - 1 ? `${v}+` : String(v),
              value: points_probs[i] * 100,
              tip: `${i === points_bins.length - 1 ? `${v} or more` : v} points`,
            }))}
            format={(v) => `${v.toFixed(0)}%`}
            color="#1c5cab"
            height={compact ? 170 : 200}
          />
        </Card>
      )}

      <div className={`grid gap-4 ${compact ? "" : "lg:grid-cols-2"}`}>
        <Card title="Points per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.points, tip: label(m) }))} format={(v) => v.toFixed(0)} height={160} />
        </Card>
        <Card title="Minutes per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.minutes, tip: label(m) }))} format={(v) => v.toFixed(0)} color="#5c4434" height={160} />
        </Card>
        <Card title="xG per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.xg, tip: label(m) }))} format={(v) => v.toFixed(2)} height={160} />
        </Card>
        <Card title="xA per match">
          <Bars bars={matches.map((m) => ({ label: `${m.gw}`, value: m.xa, tip: label(m) }))} format={(v) => v.toFixed(2)} height={160} />
        </Card>
      </div>

      <Card title="Match history">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="py-1.5 text-left">GW</th>
                <th className="py-1.5 text-left">Opp</th>
                <th className="py-1.5 text-right">Mins</th>
                <th className="py-1.5 text-right">Pts</th>
                <th className="py-1.5 text-right">xG</th>
                <th className="py-1.5 text-right">xA</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {[...matches].reverse().map((m, i) => (
                <tr key={i}>
                  <td className="py-1.5">{m.gw}</td>
                  <td className="py-1.5">
                    {m.opponent} ({m.home ? "H" : "A"})
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{m.minutes}</td>
                  <td className="py-1.5 text-right font-semibold tabular-nums">{m.points}</td>
                  <td className="py-1.5 text-right tabular-nums">{m.xg.toFixed(2)}</td>
                  <td className="py-1.5 text-right tabular-nums">{m.xa.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-cream p-4 shadow-sm ring-1 ring-line">
      <h3 className="font-bold">{title}</h3>
      {note && <p className="text-sm text-muted">{note}</p>}
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-gold-soft">{label}</div>
      <div className="text-xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-2xl bg-cream p-3 shadow-sm ring-1 ring-line">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className="text-2xl font-black tabular-nums text-gold-deep">{value}</div>
      <div className="text-[11px] text-muted">{note}</div>
    </div>
  );
}
