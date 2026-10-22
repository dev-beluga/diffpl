"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PlayerSheet } from "@/components/PlayerSheet";
import { Failed, Spinner } from "@/components/States";
import type { ExposureRow, LeagueView, Target } from "@/lib/api";
import { LAST_LEAGUE_KEY, remember } from "@/lib/storage";
import { useApi } from "@/lib/useApi";

export default function LeaguePage() {
  const { id } = useParams<{ id: string }>();
  const team = useSearchParams().get("team");
  const teamId = team && /^\d+$/.test(team) ? Number(team) : null;
  const res = useApi<LeagueView>(`/api/league/${id}${teamId ? `?team=${teamId}` : ""}`);
  const [player, setPlayer] = useState<number | null>(null);

  useEffect(() => {
    if (res.status === "ok") remember(LAST_LEAGUE_KEY, res.data.league_id);
  }, [res]);

  if (res.status === "loading") return <Spinner label="Loading league" />;
  if (res.status === "error") return <Failed message={res.message} />;
  const v = res.data;
  const me = v.standings.find((s) => s.entry_id === teamId);

  return (
    <div className="flex flex-col gap-5">
      <PlayerSheet id={player} onClose={() => setPlayer(null)} />
      <section className="flex flex-wrap items-end justify-between gap-3 rounded-2xl bg-espresso p-5 text-cream">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-gold">League {v.league_id}</div>
          <h1 className="text-2xl font-black">Mini-league, up to GW{v.gw}</h1>
          <div className="text-sm text-sand-deep">{v.managers} managers imported</div>
        </div>
        {me && (
          <div className="text-right">
            <div className="text-xs uppercase tracking-wider text-gold-soft">{me.entry_name}</div>
            <div className="text-3xl font-black tabular-nums">#{me.rank}</div>
            <div className="text-sm text-sand-deep">{me.gap ? `${me.gap} pts behind the leader` : "Leading"}</div>
          </div>
        )}
      </section>

      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <Panel title="Standings">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="py-1.5 text-left">#</th>
                <th className="py-1.5 text-left">Team</th>
                <th className="py-1.5 text-right">Pts</th>
                <th className="py-1.5 text-right">Gap</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {v.standings.map((s) => (
                <tr key={s.entry_id} className={s.entry_id === teamId ? "bg-gold-soft/60 font-semibold" : ""}>
                  <td className="py-1.5 tabular-nums">{s.rank}</td>
                  <td className="py-1.5">
                    {s.entry_name}
                    <span className="ml-1.5 text-xs text-muted">{s.manager}</span>
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{s.total_points}</td>
                  <td className="py-1.5 text-right tabular-nums text-muted">{s.gap ? `-${s.gap}` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <div className="flex flex-col gap-5">
          {teamId ? (
            <>
              <Panel title="Your differentials" note="You own them; the league mostly does not. You gain when they score.">
                <ExposureList rows={v.differentials} onSelect={setPlayer} />
              </Panel>
              <Panel title="Threats" note="The league owns or captains them; you do not. You lose ground when they score.">
                <ExposureList rows={v.threats} onSelect={setPlayer} />
              </Panel>
            </>
          ) : (
            <Panel title="Your exposure">
              <p className="text-sm text-ink-soft">Add your team id to the URL (?team=…) to see differentials and threats.</p>
            </Panel>
          )}
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel
          title="Template you are missing"
          note={`Owned by at least 20% of the ${v.reference}, not in your squad. Sorted by that ownership.`}
        >
          <Targets rows={v.template_targets} primary="reference" onSelect={setPlayer} />
        </Panel>
        <Panel
          title="Differentials to beat your rivals"
          note="Most expected points over the next 4 GWs among players at most 10% of this league owns."
        >
          <Targets rows={v.differential_targets} primary="xp" onSelect={setPlayer} />
        </Panel>
      </div>
    </div>
  );
}

function Panel({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl bg-cream p-4 shadow-sm ring-1 ring-line">
      <h2 className="font-bold">{title}</h2>
      {note && <p className="text-sm text-muted">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ExposureList({ rows, onSelect }: { rows: ExposureRow[]; onSelect: (id: number) => void }) {
  if (!rows.length) return <p className="text-sm text-ink-soft">None this GW.</p>;
  return (
    <ul className="divide-y divide-line text-sm">
      {rows.map((r) => (
        <li key={r.element_id} className="flex items-center justify-between py-1.5">
          <button onClick={() => onSelect(r.element_id)} className="text-left font-semibold hover:text-gold-deep">
            {r.name}
            <span className="ml-1.5 text-xs font-normal text-muted">
              {r.team} · {r.position}
              {r.mine >= 2 ? " · your captain" : ""}
            </span>
          </button>
          <span className="tabular-nums text-ink-soft">
            {r.ownership.toFixed(0)}% owned · EO {r.effective_ownership.toFixed(0)}%
          </span>
        </li>
      ))}
    </ul>
  );
}

function Targets({
  rows,
  primary,
  onSelect,
}: {
  rows: Target[];
  primary: "reference" | "xp";
  onSelect: (id: number) => void;
}) {
  if (!rows.length) return <p className="text-sm text-ink-soft">No players match yet.</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-xs uppercase tracking-wider text-muted">
        <tr>
          <th className="py-1.5 text-left">Player</th>
          <th className="py-1.5 text-right">£m</th>
          <th className="py-1.5 text-right">xP 4 GW</th>
          <th className="py-1.5 text-right">Top 100</th>
          <th className="py-1.5 text-right">League</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {rows.map((t) => (
          <tr key={t.element_id}>
            <td className="py-1.5">
              <button onClick={() => onSelect(t.element_id)} className="text-left font-semibold hover:text-gold-deep">
                {t.name}
              </button>
              <span className="ml-1.5 text-xs text-muted">
                {t.team} · {t.position}
              </span>
            </td>
            <td className="py-1.5 text-right tabular-nums">{t.price.toFixed(1)}</td>
            <td className={`py-1.5 text-right tabular-nums ${primary === "xp" ? "font-bold text-gold-deep" : ""}`}>
              {t.xp_horizon.toFixed(1)}
            </td>
            <td className={`py-1.5 text-right tabular-nums ${primary === "reference" ? "font-bold text-gold-deep" : ""}`}>
              {t.reference_ownership.toFixed(0)}%
            </td>
            <td className="py-1.5 text-right tabular-nums">{t.league_ownership.toFixed(0)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
