"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Pitch } from "@/components/Pitch";
import { PlayerSheet } from "@/components/PlayerSheet";
import { fetchPlan, type GwPlan, type Plan } from "@/lib/api";
import { rememberTeam } from "@/lib/storage";

export default function TeamPage() {
  const { id } = useParams<{ id: string }>();
  const teamId = Number(id);
  const [data, setData] = useState<GwPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [player, setPlayer] = useState<number | null>(null);

  useEffect(() => {
    if (!Number.isInteger(teamId) || teamId <= 0) {
      setError("That is not a valid team id.");
      return;
    }
    const ctrl = new AbortController();
    setData(null);
    setError(null);
    fetchPlan(teamId, ctrl.signal)
      .then((d) => {
        setData(d);
        setSelected(0);
        rememberTeam(teamId);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => ctrl.abort();
  }, [teamId]);

  if (error) return <ErrorState message={error} />;
  if (!data) return <Loading />;
  const plan = data.plans[selected];

  return (
    <div className="flex flex-col gap-5">
      <PlayerSheet id={player} onClose={() => setPlayer(null)} />
      <Summary data={data} />
      <PlanTabs plans={data.plans} selected={selected} onSelect={setSelected} />
      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <Pitch starters={plan.starters} bench={plan.bench} onSelect={setPlayer} />
        <aside className="flex flex-col gap-4">
          <Transfers plan={plan} horizon={data.horizon} freeTransfers={data.free_transfers} />
          <Captain plan={plan} />
          <p className="text-xs leading-relaxed text-muted">
            Plans maximize expected points over the next {data.horizon} GWs. Player data as of{" "}
            {new Date(data.data_as_of).toUTCString().slice(5, 22)} UTC; your picks up to GW{data.picks_gw}. Selling
            prices are taken as current prices because purchase prices are private.
          </p>
          {data.picks_gw < data.gw - 1 && (
            <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800 ring-1 ring-amber-200">
              Your picks are older than the last deadline, so this plan may start from an old squad.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

function Summary({ data }: { data: GwPlan }) {
  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat label={`GW${data.gw} deadline`} value={<Countdown deadline={data.deadline} />} />
      <Stat label="Bank" value={`£${data.bank.toFixed(1)}m`} />
      <Stat label="Free transfers" value={String(data.free_transfers)} />
      <Stat label="Squad value" value={`£${data.squad_value.toFixed(1)}m`} />
    </section>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-cream p-4 shadow-sm ring-1 ring-line">
      <div className="text-xs font-medium uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
    </div>
  );
}

function Countdown({ deadline }: { deadline: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  const ms = new Date(deadline).getTime() - now;
  if (ms <= 0) return <span className="text-rose-600">Passed</span>;
  const d = Math.floor(ms / 86_400_000);
  const h = Math.floor((ms % 86_400_000) / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return <span>{d > 0 ? `${d}d ${h}h` : `${h}h ${m}m`}</span>;
}

function PlanTabs({ plans, selected, onSelect }: { plans: Plan[]; selected: number; onSelect: (i: number) => void }) {
  const best = plans[0]?.objective ?? 0;
  return (
    <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Plans">
      {plans.map((p, i) => (
        <button
          key={p.rank}
          role="tab"
          aria-selected={i === selected}
          onClick={() => onSelect(i)}
          className={`shrink-0 rounded-xl px-4 py-2 text-left text-sm shadow-sm ring-1 transition ${
            i === selected ? "bg-espresso text-white ring-espresso" : "bg-cream text-ink-soft ring-line hover:ring-cocoa"
          }`}
        >
          <div className="font-semibold">
            Plan {p.rank}
            {i === 0 && <span className="ml-1.5 rounded bg-gold px-1.5 py-0.5 text-[10px] font-bold text-white">BEST</span>}
          </div>
          <div className={`text-xs ${i === selected ? "text-gold-soft" : "text-muted"}`}>
            {p.transfers.length} transfer{p.transfers.length === 1 ? "" : "s"}
            {p.hits ? ` · -${p.hits}` : ""}
            {i > 0 && ` · ${(p.objective - best).toFixed(1)} xP`}
          </div>
        </button>
      ))}
    </div>
  );
}

function Transfers({ plan, horizon, freeTransfers }: { plan: Plan; horizon: number; freeTransfers: number }) {
  return (
    <section className="rounded-2xl bg-cream p-4 shadow-sm ring-1 ring-line">
      <h2 className="text-sm font-bold uppercase tracking-wider text-muted">Transfers</h2>
      {plan.transfers.length === 0 ? (
        <p className="mt-2 text-sm text-ink-soft">
          No transfers. Roll {freeTransfers === 1 ? "the free transfer" : `your ${freeTransfers} free transfers`}.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {plan.transfers.map((t) => (
            <li key={`${t.out.element_id}-${t.into.element_id}`} className="rounded-xl bg-sand p-3 ring-1 ring-line">
              <div className="flex items-center justify-between text-sm">
                <span className="truncate">
                  <span className="mr-1.5 text-xs font-bold text-rose-600">OUT</span>
                  {t.out.name}
                </span>
                <span className="tabular-nums text-muted">£{t.out.price.toFixed(1)}m</span>
              </div>
              <div className="mt-1 flex items-center justify-between text-sm">
                <span className="truncate font-semibold">
                  <span className="mr-1.5 text-xs font-bold text-pitch">IN</span>
                  {t.into.name}
                </span>
                <span className="tabular-nums text-muted">£{t.into.price.toFixed(1)}m</span>
              </div>
              <div className={`mt-1.5 text-xs font-medium ${t.gain >= 0 ? "text-gold-deep" : "text-rose-700"}`}>
                {t.gain >= 0 ? "+" : ""}
                {t.gain.toFixed(1)} xP over {horizon} GWs
              </div>
            </li>
          ))}
        </ul>
      )}
      {plan.hits > 0 && <p className="mt-3 text-sm font-semibold text-rose-700">Costs a {plan.hits}-point hit.</p>}
    </section>
  );
}

function Captain({ plan }: { plan: Plan }) {
  const cap = plan.starters.find((p) => p.captain);
  const vice = plan.starters.find((p) => p.vice);
  if (!cap) return null;
  return (
    <section className="rounded-2xl bg-cream p-4 shadow-sm ring-1 ring-line">
      <h2 className="text-sm font-bold uppercase tracking-wider text-muted">Armband</h2>
      <div className="mt-2 flex items-baseline justify-between">
        <span className="text-lg font-bold">{cap.name}</span>
        <span className="tabular-nums text-ink-soft">{(cap.xp * 2).toFixed(1)} xP</span>
      </div>
      {vice && <div className="mt-1 text-sm text-muted">Vice: {vice.name}</div>}
    </section>
  );
}

function Loading() {
  return (
    <div className="flex flex-col items-center gap-4 py-24 text-center">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-soft border-t-gold-deep" />
      <div className="font-semibold">Solving your plans</div>
      <p className="max-w-sm text-sm text-muted">
        Projections for every player, then an optimizer over the next GWs. The first request can take a minute or two;
        after that it is cached.
      </p>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="mx-auto max-w-md py-24 text-center">
      <div className="text-lg font-semibold">Could not plan this team</div>
      <p className="mt-2 text-sm text-ink-soft">{message}</p>
      <Link href="/" className="mt-6 inline-block text-sm font-medium text-gold-deep hover:underline">
        Try another team id
      </Link>
    </div>
  );
}
