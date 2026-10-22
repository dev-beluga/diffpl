// Approximate home kits for 2026-27 clubs, drawn as SVG. No club or FPL artwork is used.

export interface Kit {
  body: string;
  sleeves: string;
  trim: string;
  stripes?: string; // second colour for vertical stripes
}

export const KITS: Record<string, Kit> = {
  ARS: { body: "#DB0007", sleeves: "#FFFFFF", trim: "#FFFFFF" },
  AVL: { body: "#7A1E43", sleeves: "#9BC3E6", trim: "#9BC3E6" },
  BOU: { body: "#D71920", sleeves: "#111111", trim: "#111111", stripes: "#111111" },
  BRE: { body: "#E30613", sleeves: "#E30613", trim: "#111111", stripes: "#FFFFFF" },
  BHA: { body: "#0057B8", sleeves: "#0057B8", trim: "#FFFFFF", stripes: "#FFFFFF" },
  CHE: { body: "#034694", sleeves: "#034694", trim: "#FFFFFF" },
  COV: { body: "#6CC6EA", sleeves: "#6CC6EA", trim: "#FFFFFF" },
  CRY: { body: "#1B458F", sleeves: "#1B458F", trim: "#C4122E", stripes: "#C4122E" },
  EVE: { body: "#003399", sleeves: "#003399", trim: "#FFFFFF" },
  FUL: { body: "#FFFFFF", sleeves: "#FFFFFF", trim: "#111111" },
  HUL: { body: "#F5A12D", sleeves: "#F5A12D", trim: "#111111", stripes: "#111111" },
  IPS: { body: "#3A64A3", sleeves: "#3A64A3", trim: "#FFFFFF" },
  LEE: { body: "#FFFFFF", sleeves: "#FFFFFF", trim: "#1D428A" },
  LIV: { body: "#C8102E", sleeves: "#C8102E", trim: "#F6EB61" },
  MCI: { body: "#6CABDD", sleeves: "#6CABDD", trim: "#FFFFFF" },
  MUN: { body: "#DA291C", sleeves: "#DA291C", trim: "#111111" },
  NEW: { body: "#FFFFFF", sleeves: "#111111", trim: "#111111", stripes: "#111111" },
  NFO: { body: "#DD0000", sleeves: "#DD0000", trim: "#FFFFFF" },
  TOT: { body: "#FFFFFF", sleeves: "#FFFFFF", trim: "#132257" },
  SUN: { body: "#EB172B", sleeves: "#EB172B", trim: "#111111", stripes: "#FFFFFF" },
};

export const GOALKEEPER_KIT: Kit = { body: "#F2C300", sleeves: "#1E1E1E", trim: "#1E1E1E" };
export const UNKNOWN_KIT: Kit = { body: "#9AA5B1", sleeves: "#7B8794", trim: "#FFFFFF" };

export function kitFor(team: string, goalkeeper: boolean): Kit {
  if (goalkeeper) return GOALKEEPER_KIT;
  return KITS[team] ?? UNKNOWN_KIT;
}
