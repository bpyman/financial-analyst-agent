import type { RuntimeKind } from "./types";

/**
 * A link that asks one question: `/?q=<question>&rt=recorded|live`. It holds
 * the question only, never a thread, so opening it starts a new conversation
 * and no visitor's state travels in the URL (ADR 0006 keeps threads private).
 */
export interface SharedQuestion {
  question: string;
  /** null: the deployment's default runtime. */
  runtime: RuntimeKind | null;
}

export function shareLink(origin: string, question: string, runtime: RuntimeKind | null): string {
  const params = new URLSearchParams({ q: question.trim() });
  if (runtime) params.set("rt", runtime);
  return `${origin}/?${params.toString()}`;
}

/** The question a page was opened to ask, or null when it names none the composer would take. */
export function parseShareLink(search: string, maxChars: number): SharedQuestion | null {
  const params = new URLSearchParams(search);
  const question = (params.get("q") ?? "").trim();
  if (!question || question.length > maxChars) return null;
  const rt = params.get("rt");
  return { question, runtime: rt === "recorded" || rt === "live" ? rt : null };
}
