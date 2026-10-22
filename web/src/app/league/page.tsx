"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LAST_LEAGUE_KEY, LAST_TEAM_KEY, recall } from "@/lib/storage";

const ID = /^\d{1,8}$/;

export default function LeagueEntry() {
  const router = useRouter();
  const [league, setLeague] = useState("");
  const [team, setTeam] = useState("");

  useEffect(() => {
    setLeague(recall(LAST_LEAGUE_KEY) ?? "");
    setTeam(recall(LAST_TEAM_KEY) ?? "");
  }, []);

  const valid = ID.test(league) && (team === "" || ID.test(team));
  return (
    <div className="mx-auto max-w-xl py-16 text-center">
      <h1 className="text-4xl font-black tracking-tight">Mini-league</h1>
      <p className="mt-3 text-ink-soft">
        Standings, where you differ from your rivals, and transfer targets from the top 100 and your league.
      </p>
      <form
        className="mt-8 flex flex-col gap-3 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) router.push(`/league/${league}${team ? `?team=${team}` : ""}`);
        }}
      >
        <input
          inputMode="numeric"
          placeholder="League id"
          value={league}
          onChange={(e) => setLeague(e.target.value.trim())}
          aria-label="League id"
          className="flex-1 rounded-xl border border-line bg-cream px-4 py-3 shadow-sm outline-none focus:border-gold"
        />
        <input
          inputMode="numeric"
          placeholder="Your team id (optional)"
          value={team}
          onChange={(e) => setTeam(e.target.value.trim())}
          aria-label="Your team id"
          className="flex-1 rounded-xl border border-line bg-cream px-4 py-3 shadow-sm outline-none focus:border-gold"
        />
        <button
          type="submit"
          disabled={!valid}
          className="rounded-xl bg-gold-deep px-6 py-3 font-semibold text-white shadow-sm hover:bg-espresso disabled:opacity-40"
        >
          Open
        </button>
      </form>
      <p className="mt-3 text-xs text-muted">
        The league id is in its standings URL: fantasy.premierleague.com/leagues/<b>123456</b>/standings/c. The league
        must be ingested first: <code>python -m diffpl.ingest league --id &lt;id&gt;</code>.
      </p>
    </div>
  );
}
