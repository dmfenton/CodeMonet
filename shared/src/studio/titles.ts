/**
 * Piece titles: title -> prompt (truncated) -> "Piece N". Never invented.
 */

export interface TitleSource {
  title?: string | null;
  prompt?: string | null;
  pieceNumber: number;
}

/** Longest prompt shown as a title before truncating at a word boundary. */
export const PROMPT_TITLE_MAX = 56;

/** Collapse whitespace and cut at a word boundary, adding an ellipsis. */
export function truncateText(text: string, max: number): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean.length <= max) return clean;
  const cut = clean.slice(0, max);
  const lastSpace = cut.lastIndexOf(' ');
  const head = lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut;
  return `${head.replace(/[\s,.;:–—-]+$/, '')}…`;
}

export function pieceDisplayTitle({ title, prompt, pieceNumber }: TitleSource): string {
  const named = title?.trim();
  if (named) return named;
  const asked = prompt?.trim();
  if (asked) return truncateText(asked, PROMPT_TITLE_MAX);
  return `Piece ${pieceNumber}`;
}
