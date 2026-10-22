// Per-browser conveniences only: the last team and league used. Nothing else is stored.
export const LAST_TEAM_KEY = "diffpl:lastTeam";
export const LAST_LEAGUE_KEY = "diffpl:lastLeague";

export function remember(key: string, value: number): void {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // storage blocked (private window): the URL still carries the ids
  }
}

export function recall(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function rememberTeam(teamId: number): void {
  remember(LAST_TEAM_KEY, teamId);
}
