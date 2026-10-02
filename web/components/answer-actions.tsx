"use client";

import { Check, Copy, Download } from "lucide-react";
import { useEffect, useState } from "react";
import { answerFileName, answerMarkdown } from "@/lib/answer-text";
import { cn } from "@/lib/format";
import type { Presentation } from "@/lib/types";

const ACTION =
  "inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[12px] font-medium text-muted transition-colors " +
  "hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";

/**
 * Copy an answer, or save it as a Markdown file, with its sources: the figures
 * as shown (the table in its current order) and a link to every filing read.
 */
export function AnswerActions({
  question,
  presentation,
  rowOrder,
}: {
  question: string;
  presentation: Presentation;
  rowOrder: number[] | null;
}) {
  const [copied, setCopied] = useState<"copied" | "failed" | null>(null);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(null), copied === "failed" ? 4000 : 1800);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const text = () => answerMarkdown(question, presentation, rowOrder);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text());
      setCopied("copied");
    } catch {
      // Clipboard can be blocked (insecure origin, permissions); saving still works, so say so.
      setCopied("failed");
    }
  }

  function save() {
    const url = URL.createObjectURL(new Blob([text()], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = answerFileName(question);
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  return (
    <div className="flex items-center gap-0.5">
      <button
        type="button"
        onClick={copy}
        title="Copy this answer with its sources, as Markdown"
        className={cn(
          ACTION,
          copied === "copied" && "text-positive hover:text-positive",
          copied === "failed" && "text-negative hover:text-negative",
        )}
      >
        {copied === "copied" ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
        {copied === "copied" ? "Copied" : copied === "failed" ? "Couldn't copy; use Save" : "Copy with sources"}
        <span className="sr-only" aria-live="polite">
          {copied === "copied" ? "Answer copied" : copied === "failed" ? "Couldn't copy the answer. Save it instead." : ""}
        </span>
      </button>
      <button
        type="button"
        onClick={save}
        title="Save this answer with its sources as a Markdown file"
        aria-label="Save answer as Markdown"
        className={ACTION}
      >
        <Download className="size-3.5" aria-hidden />
        <span className="hidden sm:inline">Save</span>
      </button>
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
