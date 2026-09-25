import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ValueKind } from "./types";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Axis tick labels only. Reported amounts shown as text always come from the
 * server's presentation mapping (ADR 0006); ticks are a scale, not a fact.
 */
export function axisTick(value: number, kind: ValueKind): string {
  if (!Number.isFinite(value)) return "";
  if (kind === "percent") return `${Number((value * 100).toFixed(1))}%`;
  if (kind === "multiple") return `${value.toFixed(1)}x`;
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const scaled = (divisor: number, suffix: string) => {
    const n = abs / divisor;
    const digits = n >= 100 ? 0 : n >= 10 ? 1 : 2;
    return `${sign}$${Number(n.toFixed(digits))}${suffix}`;
  };
  if (abs >= 1e12) return scaled(1e12, "T");
  if (abs >= 1e9) return scaled(1e9, "B");
  if (abs >= 1e6) return scaled(1e6, "M");
  if (abs >= 1e3) return scaled(1e3, "K");
  return `${sign}$${abs.toFixed(0)}`;
}

const MD_LINK = /^\[([^\]]+)\]\(([^)]+)\)$/;

/** Trace values arrive as plain text or a single markdown link. */
export function parseLink(value: string): { text: string; href: string } | null {
  const match = MD_LINK.exec(value);
  if (!match) return null;
  const [, text, href] = match;
  return safeHref(href) ? { text, href } : null;
}

export function safeHref(href: string): boolean {
  try {
    const url = new URL(href);
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}
