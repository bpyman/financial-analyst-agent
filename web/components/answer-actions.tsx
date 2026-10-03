"use client";

import { Check, Copy, Download, Link2, Sheet } from "lucide-react";
import { useEffect, useState } from "react";
import { answerFileName, answerMarkdown } from "@/lib/answer-text";
import { csvFileName, tableCsv } from "@/lib/csv";
import { cn } from "@/lib/format";
import { shareLink } from "@/lib/share-link";
import type { DisplayTable, Presentation, RuntimeKind } from "@/lib/types";

const ACTION =
  "inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[12px] font-medium text-muted transition-colors " +
  "hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";

type Copied = { what: "answer" | "link"; ok: boolean } | null;

/**
 * Copy an answer, or save it as a Markdown file, with its sources: the figures
 * as shown (the table in its current order and layout) and a link to every
 * filing read. Copy link shares the conversation up to this answer; CSV saves the table's
 * exact amounts.
 */
export function AnswerActions({
  question,
  conversation,
  presentation,
  table,
  rowOrder,
  runtime,
}: {
  question: string;
  /** Every message sent up to this answer, which a shared link asks again in order. */
  conversation: string[];
  presentation: Presentation;
  /** The table as on screen, when there is one. */
  table: DisplayTable | null;
  rowOrder: number[] | null;
  /** The thread's runtime, for the shared link; null leaves it to the deployment. */
  runtime: RuntimeKind | null;
}) {
  const [copied, setCopied] = useState<Copied>(null);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(null), copied.ok ? 1800 : 4000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copy(what: "answer" | "link") {
    const text =
      what === "answer"
        ? answerMarkdown(question, presentation, rowOrder, table)
        : shareLink(window.location.origin, conversation, runtime);
    try {
      await navigator.clipboard.writeText(text);
      setCopied({ what, ok: true });
    } catch {
      // Clipboard can be blocked (insecure origin, permissions); saving still works, so say so.
      setCopied({ what, ok: false });
    }
  }

  function download(text: string, type: string, name: string) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  const answerState = copied?.what === "answer" ? copied : null;
  const linkState = copied?.what === "link" ? copied : null;
  return (
    <div className="flex flex-wrap items-center justify-end gap-0.5">
      <button
        type="button"
        onClick={() => void copy("answer")}
        title="Copy this answer with its sources, as Markdown"
        className={cn(
          ACTION,
          answerState?.ok && "text-positive hover:text-positive",
          answerState && !answerState.ok && "text-negative hover:text-negative",
        )}
      >
        {answerState?.ok ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
        {answerState?.ok ? "Copied" : answerState ? "Couldn't copy; use Save" : "Copy with sources"}
      </button>
      {question.trim() && (
        <button
          type="button"
          onClick={() => void copy("link")}
          title="Copy a link that asks this question in a new conversation"
          aria-label={linkState?.ok ? "Link copied" : "Copy link"}
          className={cn(
            ACTION,
            linkState?.ok && "text-positive hover:text-positive",
            linkState && !linkState.ok && "text-negative hover:text-negative",
          )}
        >
          {linkState?.ok ? <Check className="size-3.5" aria-hidden /> : <Link2 className="size-3.5" aria-hidden />}
          <span className="hidden sm:inline">{linkState?.ok ? "Copied" : linkState ? "Couldn't copy" : "Copy link"}</span>
        </button>
      )}
      {table && table.rows.length > 0 && (
        <button
          type="button"
          onClick={() => download(tableCsv(table, rowOrder), "text/csv;charset=utf-8", csvFileName(question))}
          title="Save the table as CSV, in its current order, with exact amounts"
          aria-label="Save table as CSV"
          className={ACTION}
        >
          <Sheet className="size-3.5" aria-hidden />
          <span className="hidden sm:inline">CSV</span>
        </button>
      )}
      <button
        type="button"
        onClick={() =>
          download(
            answerMarkdown(question, presentation, rowOrder, table),
            "text/markdown;charset=utf-8",
            answerFileName(question),
          )
        }
        title="Save this answer with its sources as a Markdown file"
        aria-label="Save answer as Markdown"
        className={ACTION}
      >
        <Download className="size-3.5" aria-hidden />
        <span className="hidden sm:inline">Save</span>
      </button>
      <span className="sr-only" aria-live="polite">
        {answerState?.ok
          ? "Answer copied"
          : answerState
            ? "Couldn't copy the answer. Save it instead."
            : linkState?.ok
              ? "Link copied"
              : linkState
                ? "Couldn't copy the link."
                : ""}
      </span>
    </div>
  );
}

/** Whether an answer has figures or text worth taking away (not a clarify or a greeting). */
export function hasTakeaway(presentation: Presentation): boolean {
  return Boolean(
    presentation.fact_card ||
      (presentation.table && presentation.table.rows.length > 0) ||
      presentation.essay ||
      presentation.disclosures.length > 0,
  );
}
