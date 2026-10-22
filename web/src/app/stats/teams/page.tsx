"use client";

import { TeamScatter } from "@/components/charts/TeamScatter";
import { Failed, Spinner } from "@/components/States";
import type { TeamForm } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export default function TeamsPage() {
  const res = useApi<TeamForm[]>("/api/stats/teams");
  if (res.status === "loading") return <Spinner label="Loading teams" />;
  if (res.status === "error") return <Failed message={res.message} />;
  const teams = res.data;
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
      <section className="rounded-2xl bg-cream p-5 shadow-sm ring-1 ring-line">
        <h2 className="font-bold">Attack vs defence, last 5 matches</h2>
        <p className="text-sm text-muted">Team xG is the sum of its players&apos; xG. Dashed lines: league average.</p>
        <div className="mt-3">
          <TeamScatter teams={teams} />
        </div>
      </section>
      <section className="overflow-hidden rounded-2xl bg-cream shadow-sm ring-1 ring-line">
        <table className="w-full text-sm">
          <thead className="bg-sand text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2.5 text-left">Team</th>
              <th className="px-3 py-2.5 text-right">xG</th>
              <th className="px-3 py-2.5 text-right">xGA</th>
              <th className="px-3 py-2.5 text-right">GF</th>
              <th className="px-3 py-2.5 text-right">GA</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {[...teams]
              .sort((a, b) => b.xg_for - b.xg_against - (a.xg_for - a.xg_against))
              .map((t) => (
                <tr key={t.team}>
                  <td className="px-3 py-2 font-semibold">{t.team}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{t.xg_for.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{t.xg_against.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{t.goals_for.toFixed(1)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{t.goals_against.toFixed(1)}</td>
                </tr>
              ))}
          </tbody>
        </table>
        <p className="px-3 py-2 text-xs text-muted">Per match, last 5. Sorted by xG difference.</p>
      </section>
    </div>
  );
}
