"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { LAST_TEAM_KEY } from "@/lib/storage";

export default function Home() {
  const router = useRouter();
  const [team, setTeam] = useState("");
  const [last, setLast] = useState<string | null>(null);

  useEffect(() => {
    try {
      setLast(localStorage.getItem(LAST_TEAM_KEY));
    } catch {
      // storage blocked: nothing remembered
    }
  }, []);

  const valid = /^\d{1,8}$/.test(team) && Number(team) > 0;

  return (
    <div className="mx-auto max-w-xl py-16 text-center">
      <h1 className="text-4xl font-black tracking-tight sm:text-5xl">Plan your gameweek</h1>
      <p className="mt-3 text-ink-soft">
        Transfers, captain and lineup from calibrated projections and an optimizer, checked against past seasons.
      </p>
      <form
        className="mt-8 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) router.push(`/team/${team}`);
        }}
      >
        <input
          inputMode="numeric"
          placeholder="Your FPL team id"
          value={team}
          onChange={(e) => setTeam(e.target.value.trim())}
          className="flex-1 rounded-xl border border-line bg-cream px-4 py-3 text-lg shadow-sm outline-none focus:border-gold focus:ring-2 focus:ring-gold-soft"
          aria-label="FPL team id"
        />
        <button
          type="submit"
          disabled={!valid}
          className="rounded-xl bg-gold-deep px-6 py-3 font-semibold text-white shadow-sm transition hover:bg-espresso disabled:opacity-40"
        >
          Plan
        </button>
      </form>
      <p className="mt-3 text-xs text-muted">
        It is the number in your FPL points page URL: fantasy.premierleague.com/entry/<b>1234567</b>/event/7
      </p>
      {last && (
        <button
          onClick={() => router.push(`/team/${last}`)}
          className="mt-6 text-sm font-medium text-gold-deep underline-offset-4 hover:underline"
        >
          Continue with team {last}
        </button>
      )}
    </div>
  );
}
