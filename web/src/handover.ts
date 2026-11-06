// Hand-over of a project description to "Build a team" from another page (Find
// researchers, the Funding idea box): kept in this tab only and read once, so the text
// never goes into an address. A small module of its own, so those pages do not load
// the team code.
const HANDOVER = "atlas-team-text";
export function handTextToTeam(text: string): void {
  try { sessionStorage.setItem(HANDOVER, text); } catch { /* storage unavailable: the box starts empty */ }
}
export function takeHandedText(): string {
  try {
    const t = sessionStorage.getItem(HANDOVER) ?? "";
    sessionStorage.removeItem(HANDOVER);
    return t;
  } catch { return ""; }
}
