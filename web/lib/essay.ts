import { safeHref } from "./format";

const SOURCE_PREFIX = "#source-";

// "[n]" not already a link ("[n](…)") or a definition ("[n]: …").
const MARKER = /\[(\d{1,3})\](?![(:])/g;

/**
 * Turns an essay's [n] source markers (the news brief cites this way) into
 * in-page links the renderer draws as citation chips. A marker with no
 * matching source stays plain text.
 */
export function linkCitations(essay: string, count: number): string {
  if (count <= 0) return essay;
  return essay.replace(MARKER, (marker, digits: string) => {
    const index = Number(digits);
    return index >= 1 && index <= count ? `[${index}](${SOURCE_PREFIX}${index})` : marker;
  });
}

/** The source number a marker link points at, or null for any other link. */
export function citationIndex(href: string): number | null {
  if (!href.startsWith(SOURCE_PREFIX)) return null;
  const digits = href.slice(SOURCE_PREFIX.length);
  return /^\d+$/.test(digits) ? Number(digits) : null;
}

/** The site a source lives on, for the line under its title. */
export function sourceHost(url: string): string {
  if (!safeHref(url)) return "";
  return new URL(url).hostname.replace(/^www\./, "");
}
