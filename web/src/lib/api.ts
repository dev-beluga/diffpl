// Types mirror diffpl.api.plan (Pydantic models). Keep both in sync.

export type Position = "GKP" | "DEF" | "MID" | "FWD";

export interface Player {
  element_id: number;
  name: string;
  team: string;
  position: Position;
  price: number;
  xp: number;
  fixtures: string[];
  captain: boolean;
  vice: boolean;
  new: boolean;
}

export interface Transfer {
  out: Player;
  into: Player;
  gain: number;
}

export interface Plan {
  rank: number;
  objective: number;
  hits: number;
  starters: Player[];
  bench: Player[];
  transfers: Transfer[];
}

export interface GwPlan {
  team_id: number;
  gw: number;
  deadline: string;
  bank: number;
  free_transfers: number;
  squad_value: number;
  horizon: number;
  picks_gw: number;
  data_as_of: string;
  plans: Plan[];
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function fetchPlan(teamId: number, signal?: AbortSignal): Promise<GwPlan> {
  return getJson<GwPlan>(`/api/plan/${teamId}`, signal);
}

// --- Stats (diffpl.api.stats) ---------------------------------------------------------------

export interface PlayerRow {
  element_id: number;
  name: string;
  team: string;
  position: Position;
  price: number;
  ownership: number;
  minutes: number;
  points: number;
  form: number;
  xg90: number;
  xa90: number;
  xgi90: number;
}

export interface TeamForm {
  team: string;
  matches: number;
  xg_for: number;
  xg_against: number;
  goals_for: number;
  goals_against: number;
}

export interface TickerCell {
  gw: number;
  opponent: string;
  home: boolean;
  xg_for: number;
  xg_against: number;
}

export interface TickerRow {
  team: string;
  fixtures: TickerCell[];
}

export interface MatchRow {
  gw: number;
  opponent: string;
  home: boolean;
  minutes: number;
  points: number;
  xg: number;
  xa: number;
}

export interface PlayerDetail {
  row: PlayerRow;
  matches: MatchRow[];
  points_bins: number[];
  points_probs: number[];
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { signal });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}
