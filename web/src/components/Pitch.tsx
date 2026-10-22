import type { Player, Position } from "@/lib/api";
import { PlayerCard } from "./PlayerCard";

const ROWS: Position[] = ["GKP", "DEF", "MID", "FWD"];

// Half a pitch seen from behind the goal, goalkeeper at the top, as on the FPL team page.
export function Pitch({ starters, bench }: { starters: Player[]; bench: Player[] }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="relative overflow-hidden rounded-2xl shadow-xl ring-1 ring-black/10">
        <div
          className="absolute inset-0"
          style={{
            background:
              "repeating-linear-gradient(180deg, #2f9e57 0px, #2f9e57 56px, #2a9150 56px, #2a9150 112px)",
          }}
        />
        <Markings />
        <div className="relative flex min-h-[520px] flex-col justify-around gap-2 px-2 py-6 sm:min-h-[600px]">
          {ROWS.map((pos) => (
            <div key={pos} className="flex justify-center gap-1 sm:gap-4">
              {starters
                .filter((p) => p.position === pos)
                .map((p) => (
                  <PlayerCard key={p.element_id} player={p} />
                ))}
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-2xl bg-slate-100 p-3 ring-1 ring-slate-200">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Bench</div>
        <div className="flex justify-around gap-1 sm:gap-4">
          {bench.map((p, i) => (
            <div key={p.element_id} className="flex flex-col items-center gap-1">
              <span className="text-[10px] font-semibold text-slate-400">{i === 0 ? "GK" : i}</span>
              <PlayerCard player={p} bench />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Markings() {
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 140" preserveAspectRatio="none" aria-hidden="true">
      <g fill="none" stroke="#ffffff" strokeOpacity="0.45" strokeWidth="0.5" vectorEffect="non-scaling-stroke">
        <rect x="4" y="3" width="92" height="134" />
        <rect x="22" y="3" width="56" height="22" />
        <rect x="36" y="3" width="28" height="8" />
        <path d="M38 25 A14 12 0 0 0 62 25" />
        <line x1="4" y1="137" x2="96" y2="137" />
        <path d="M34 137 A16 16 0 0 1 66 137" />
      </g>
    </svg>
  );
}
