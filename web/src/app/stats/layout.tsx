"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/stats/players", label: "Players" },
  { href: "/stats/teams", label: "Teams" },
  { href: "/stats/fixtures", label: "Fixtures" },
];

export default function StatsLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-black tracking-tight">Stats</h1>
        <p className="mt-1 text-sm text-ink-soft">
          From the official FPL data, refreshed with each ingest. xG and xA are FPL&apos;s published values.
        </p>
      </div>
      <nav className="flex gap-1 border-b border-line" aria-label="Stats sections">
        {TABS.map((t) => {
          const active = path.startsWith(t.href);
          return (
            <Link
              key={t.href}
              href={t.href}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-semibold ${
                active ? "border-gold text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {t.label}
            </Link>
          );
        })}
      </nav>
      {children}
    </div>
  );
}
