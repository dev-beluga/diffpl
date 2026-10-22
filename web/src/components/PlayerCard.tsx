import type { Player } from "@/lib/api";
import { Shirt } from "./Shirt";

// FPL-style card: shirt, then a name plate and a fixture/xP strip.
export function PlayerCard({ player, bench = false }: { player: Player; bench?: boolean }) {
  const shown = player.captain ? player.xp * 2 : player.xp;
  const fixture = player.fixtures.length ? player.fixtures.join(", ") : "No match";
  return (
    <div
      className="group relative flex w-[76px] flex-col items-center sm:w-[96px]"
      title={`${player.name} · ${player.team} · £${player.price.toFixed(1)}m`}
    >
      <div className="relative">
        <div className="hidden sm:block">
          <Shirt team={player.team} goalkeeper={player.position === "GKP"} size={64} />
        </div>
        <div className="sm:hidden">
          <Shirt team={player.team} goalkeeper={player.position === "GKP"} size={48} />
        </div>
        {player.captain && <Badge className="bg-neutral-900 text-white">C</Badge>}
        {player.vice && <Badge className="bg-white text-neutral-900">V</Badge>}
        {player.new && (
          <span className="absolute -left-2 top-0 rounded-full bg-emerald-400 px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-emerald-950 shadow">
            In
          </span>
        )}
      </div>
      <div className="-mt-1 w-full overflow-hidden rounded-md shadow-lg ring-1 ring-black/10">
        <div
          className={`truncate px-1 py-[3px] text-center text-[11px] font-semibold text-white sm:text-xs ${
            player.new ? "bg-emerald-700" : bench ? "bg-slate-600" : "bg-slate-900"
          }`}
        >
          {player.name}
        </div>
        <div className="flex items-center justify-between gap-1 bg-white px-1.5 py-[2px] text-[10px] text-slate-700 sm:text-[11px]">
          <span className="truncate">{fixture}</span>
          <span className="shrink-0 font-bold text-slate-900">{shown.toFixed(1)}</span>
        </div>
      </div>
    </div>
  );
}

function Badge({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span
      className={`absolute -right-1 top-0 flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-black shadow ring-1 ring-black/20 ${className}`}
    >
      {children}
    </span>
  );
}
