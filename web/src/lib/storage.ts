// Per-browser convenience only: the last team planned. Nothing else is stored.
export const LAST_TEAM_KEY = "diffpl:lastTeam";

export function rememberTeam(teamId: number): void {
  try {
    localStorage.setItem(LAST_TEAM_KEY, String(teamId));
  } catch {
    // storage blocked (private window): the URL still carries the team id
  }
}
