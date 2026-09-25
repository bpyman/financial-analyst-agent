import { ArrowUpRight, Sparkles } from "lucide-react";
import { sourceHost } from "@/lib/essay";
import { safeHref } from "@/lib/format";
import type { DisplayCitation } from "@/lib/types";
import { SafeMarkdown } from "./markdown";
import { SectionLabel } from "./ui";

/**
 * A qualitative answer: the essay as safe markdown, its [n] markers linked to
 * the numbered sources beneath it.
 */
export function WrittenAnswer({
  essay,
  citations,
  title,
}: {
  essay: string;
  citations: DisplayCitation[];
  title: string;
}) {
  return (
    <section aria-label={title} className="overflow-hidden rounded-xl border border-border bg-surface">
      <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5 sm:px-5">
        <div className="flex items-center gap-2 text-[13px] font-medium text-fg">
          <Sparkles className="size-4 text-primary" aria-hidden />
          {title}
        </div>
        {citations.length > 0 && (
          <span className="text-[11px] tabular-nums text-subtle">
            {citations.length === 1 ? "1 source" : `${citations.length} sources`}
          </span>
        )}
      </header>
      <SafeMarkdown
        text={essay}
        citations={citations}
        className="max-w-[68ch] px-4 py-4 text-[15px] leading-[1.75] sm:px-5 sm:py-5"
      />
      {citations.length > 0 && <Sources citations={citations} />}
    </section>
  );
}

function Sources({ citations }: { citations: DisplayCitation[] }) {
  return (
    <footer className="border-t border-border bg-surface-2/40 px-4 py-3.5 sm:px-5">
      <SectionLabel>Sources</SectionLabel>
      <ol className="mt-2.5 space-y-2.5">
        {citations.map((citation) => {
          const host = sourceHost(citation.url);
          const meta = [host, citation.published].filter(Boolean).join(" · ");
          return (
            <li key={citation.index} className="flex min-w-0 items-start gap-3">
              <span className="num mt-px flex h-5 min-w-5 shrink-0 items-center justify-center rounded-md border border-primary/25 bg-primary-soft px-1 text-[10.5px] font-semibold text-primary">
                {citation.index}
              </span>
              <div className="min-w-0 flex-1">
                {safeHref(citation.url) ? (
                  <a
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="group inline text-[13px] font-medium leading-snug text-fg underline-offset-4 hover:text-primary hover:underline"
                  >
                    {citation.title}
                    <ArrowUpRight
                      className="ml-0.5 inline size-3.5 -translate-y-px text-subtle transition-colors group-hover:text-primary"
                      aria-hidden
                    />
                  </a>
                ) : (
                  <span className="text-[13px] font-medium leading-snug text-fg">{citation.title}</span>
                )}
                {meta && <div className="mt-0.5 text-[11.5px] tabular-nums text-subtle">{meta}</div>}
              </div>
            </li>
          );
        })}
      </ol>
    </footer>
  );
}
