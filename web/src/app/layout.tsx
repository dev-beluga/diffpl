import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "DiffPL",
  description: "FPL decisions under uncertainty, backed by leakage-free backtests.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} min-h-screen bg-sand font-sans text-ink antialiased`}>
        <header className="border-b-4 border-gold bg-espresso">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-bold tracking-tight text-cream">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gold text-sm text-espresso">D</span>
              DiffPL
            </Link>
            <nav className="flex items-center gap-5 text-sm font-medium text-sand-deep">
              <Link href="/" className="hover:text-gold">
                My team
              </Link>
              <Link href="/league" className="hover:text-gold">
                Mini-league
              </Link>
              <Link href="/stats/players" className="hover:text-gold">
                Stats
              </Link>
              <span className="hidden text-xs font-normal text-gold-soft/70 md:block">Read-only. Never writes to FPL.</span>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
