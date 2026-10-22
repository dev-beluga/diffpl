"use client";

import { Failed, Spinner } from "@/components/States";
import { Shirt } from "@/components/Shirt";
import type { Compare, ComparePlayer, ManagerSummary } from "@/lib/api";
import { useApi } from "@/lib/useApi";

// Two managers side by side: headline numbers, then who only you own, who you share, and who
// only they own. Captains carry a C, bench players are dimmed.
export function ComparePanel({
  leagueId,
  a,
  b,
  onSelectPlayer,
}: {
  leagueId: number;
  a: number;
  b: number;
  onSelectPlayer: (id: number) => void;
}) {
  const res = useApi<Compare>(`/api/league/${leagueId}/compare?a=${a}&b=${b}`);
  if (res.status === "loading") return <Spinner label="Comparing squads" />;
  if (res.status === "error") return <Failed message={res.message} />;
  const c = res.data;
  const diff = c.a.total_points - c.b.total_points;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-2xl bg-espresso p-4 text-cream">
        <Head m={c.a} align="left" />
        <div className="text-center">
          <div className="text-[11px] uppercase tracking-wider text-gold-soft">Gap</div>
          <div className={`text-2xl font-black tabular-nums ${diff >= 0 ? "text-gold" : "text-rose-300"}`}>
            {diff > 0 ? "+" : ""}
            {diff}
          </div>
        </div>
        <Head m={c.b} align="right" />
      </div>

      <table className="w-full text-sm">
        <tbody className="divide-y divide-line">
          <Row label={`GW${c.gw} points`} a={`${c.a.gw_points}`} b={`${c.b.gw_points}`} better={c.a.gw_points - c.b.gw_points} />
          <Row label="Hits" a={c.a.hits ? `-${c.a.hits}` : "0"} b={c.b.hits ? `-${c.b.hits}` : "0"} better={c.b.hits - c.a.hits} />
          <Row label="Chip" a={c.a.chip ?? "-"} b={c.b.chip ?? "-"} better={0} />
          <Row label="Squad value" a={`£${c.a.value.toFixed(1)}m`} b={`£${c.b.value.toFixed(1)}m`} better={c.a.value - c.b.value} />
          <Row label="Bank" a={`£${c.a.bank.toFixed(1)}m`} b={`£${c.b.bank.toFixed(1)}m`} better={0} />
          <Row label="Captain" a={captain(c, "a")} b={captain(c, "b")} better={0} />
        </tbody>
      </table>

      <div className="grid gap-3 sm:grid-cols-3">
        <Group title="Only you" tone="a" players={c.only_a} side="a" onSelect={onSelectPlayer} />
        <Group title="Both" tone="shared" players={c.shared} side="both" onSelect={onSelectPlayer} />
        <Group title={`Only ${c.b.entry_name}`} tone="b" players={c.only_b} side="b" onSelect={onSelectPlayer} />
      </div>
      <p className="text-xs text-muted">
        Squads at GW{c.gw}. xP is expected points over the next 4 GWs. Dimmed: on the bench.
      </p>
    </div>
  );
}

function captain(c: Compare, side: "a" | "b"): string {
  const all = [...c.shared, ...c.only_a, ...c.only_b];
  const cap = all.find((p) => (side === "a" ? p.mult_a : p.mult_b) >= 2);
  return cap ? cap.name : "-";
}

function Head({ m, align }: { m: ManagerSummary; align: "left" | "right" }) {
  return (
    <div className={align === "right" ? "text-right" : ""}>
      <div className="truncate text-xs text-gold-soft">
        #{m.rank} · {m.manager}
      </div>
      <div className="truncate text-lg font-black">{m.entry_name}</div>
      <div className="text-sm tabular-nums text-sand-deep">{m.total_points} pts</div>
    </div>
  );
}

function Row({ label, a, b, better }: { label: string; a: string; b: string; better: number }) {
  return (
    <tr>
      <td className={`py-1.5 text-left tabular-nums ${better > 0 ? "font-bold text-gold-deep" : ""}`}>{a}</td>
      <td className="py-1.5 text-center text-xs uppercase tracking-wider text-muted">{label}</td>
      <td className={`py-1.5 text-right tabular-nums ${better < 0 ? "font-bold text-gold-deep" : ""}`}>{b}</td>
    </tr>
  );
}

function Group({
  title,
  tone,
  players,
  side,
  onSelect,
}: {
  title: string;
  tone: "a" | "b" | "shared";
  players: ComparePlayer[];
  side: "a" | "b" | "both";
  onSelect: (id: number) => void;
}) {
  const ring = tone === "shared" ? "ring-line bg-sand" : tone === "a" ? "ring-gold bg-gold-soft/40" : "ring-cocoa/40 bg-cream";
  const xp = players.reduce((s, p) => s + p.xp, 0);
  return (
    <section className={`rounded-2xl p-3 ring-1 ${ring}`}>
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="truncate text-sm font-bold">{title}</h3>
        <span className="text-xs tabular-nums text-muted">
          {players.length} · {xp.toFixed(0)} xP
        </span>
      </div>
      <ul className="flex flex-col gap-1">
        {players.map((p) => {
          const benched = side === "a" ? p.bench_a : side === "b" ? p.bench_b : p.bench_a && p.bench_b;
          const cap = side === "a" ? p.mult_a >= 2 : side === "b" ? p.mult_b >= 2 : p.mult_a >= 2 || p.mult_b >= 2;
          return (
            <li key={p.element_id}>
              <button
                onClick={() => onSelect(p.element_id)}
                className={`flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left hover:bg-cream ${benched ? "opacity-50" : ""}`}
              >
                <Shirt team={p.team} goalkeeper={p.position === "GKP"} size={22} />
                <span className="min-w-0 flex-1 truncate text-sm font-semibold">{p.name}</span>
                {cap && (
                  <span className="rounded-full bg-espresso px-1.5 text-[10px] font-black text-cream">
                    {side === "both" ? `C ${p.mult_a >= 2 ? "you" : "them"}` : "C"}
                  </span>
                )}
                <span className="text-xs tabular-nums text-muted">{p.xp.toFixed(1)}</span>
              </button>
            </li>
          );
        })}
        {!players.length && <li className="text-sm text-muted">None</li>}
      </ul>
    </section>
  );
}
