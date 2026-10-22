"use client";

import { useParams, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ComparePanel } from "@/components/ComparePanel";
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
  const [picked, setRival] = useState<number | null>(null);

  useEffect(() => {
    if (res.status === "ok") remember(LAST_LEAGUE_KEY, res.data.league_id);
  }, [res]);

  if (res.status === "loading") return <Spinner label="Loading league" />;
  if (res.status === "error") return <Failed message={res.message} />;
  const v = res.data;
  const me = v.standings.find((s) => s.entry_id === teamId);
  const leader = v.standings[0]?.entry_id ?? null;
  const base = teamId ?? leader;
  const defaultRival = base === leader ? (v.standings[1]?.entry_id ?? null) : leader;
  const rival = picked ?? defaultRival;

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

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Panel title="Leaderboard" note="Pick a manager to compare.">
          <table className="w-full text-sm">
            <thead className="text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="py-1.5 text-left">#</th>
                <th className="py-1.5 text-left">Team</th>
                <th className="py-1.5 text-right">GW{v.gw}</th>
                <th className="py-1.5 text-right">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {v.standings.map((s) => {
                const isMe = s.entry_id === teamId;
                const isRival = s.entry_id === rival;
                return (
                  <tr
                    key={s.entry_id}
                    onClick={() => !isMe && setRival(s.entry_id)}
                    className={`transition ${isMe ? "bg-gold-soft/60 font-semibold" : "cursor-pointer hover:bg-sand"} ${
                      isRival ? "bg-espresso text-cream hover:bg-espresso" : ""
                    }`}
                  >
                    <td className="py-2 pl-1 tabular-nums">{s.rank}</td>
                    <td className="max-w-0 py-2">
                      <div className="truncate font-semibold">{s.entry_name}</div>
                      <div className={`truncate text-xs ${isRival ? "text-sand-deep" : "text-muted"}`}>{s.manager}</div>
                    </td>
                    <td className="py-2 text-right tabular-nums">{s.gw_points}</td>
                    <td className="py-2 pr-1 text-right font-semibold tabular-nums">{s.total_points}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Panel>

        <Panel title="Compare">
          {base && rival ? (
            <ComparePanel leagueId={v.league_id} a={base} b={rival} onSelectPlayer={setPlayer} />
          ) : (
            <p className="text-sm text-ink-soft">Pick a manager on the left.</p>
          )}
          {!teamId && (
            <p className="mt-3 text-xs text-muted">
              Comparing against the leader. Add your team id (?team=…) to compare against yourself.
            </p>
          )}
        </Panel>
      </div>

      {teamId && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="Your differentials" note="You own them; the league mostly does not. You gain when they score.">
            <ExposureList rows={v.differentials} onSelect={setPlayer} />
          </Panel>
          <Panel title="Threats" note="The league owns or captains them; you do not. You lose ground when they score.">
            <ExposureList rows={v.threats} onSelect={setPlayer} />
          </Panel>
        </div>
      )}

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
