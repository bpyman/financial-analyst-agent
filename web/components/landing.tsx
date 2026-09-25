import {
  ArrowUpRight,
  FileDiff,
  Layers,
  LineChart,
  ListOrdered,
  Loader2,
  ReceiptText,
  type LucideIcon,
} from "lucide-react";
import type { Meta } from "@/lib/types";
import { Button, Callout, SectionLabel } from "./ui";

const STORY_ICONS: Record<string, LucideIcon> = {
  "Verify a quarterly fact": ReceiptText,
  "Compare four quarters": LineChart,
  "Rank then inspect filings": ListOrdered,
  "What changed in the 10-Q": FileDiff,
};

/** First screen: guided stories, what you can ask, and the metric catalogue. */
export function Landing({
  meta,
  waking,
  error,
  disabled,
  onAsk,
  onDraft,
  onRetry,
}: {
  meta: Meta | null;
  waking: boolean;
  error: string | null;
  disabled: boolean;
  onAsk: (question: string) => void;
  onDraft: (question: string) => void;
  onRetry: () => void;
}) {
  return (
    <div className="animate-fade-up">
      <section className="pb-10 pt-8 sm:pb-12 sm:pt-14">
        <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-2.5 py-1 text-[11px] font-medium text-muted">
          <span className="size-1.5 rounded-full bg-positive shadow-[0_0_0_3px] shadow-positive/15" />
          SEC 10-Q facts with provenance on every number
        </p>
        <h1 className="mt-5 max-w-3xl text-balance text-[32px] font-semibold leading-[1.1] tracking-tight sm:text-[44px]">
          Ask about a company.{" "}
          <span className="text-muted">Get the number and the filing behind it.</span>
        </h1>
        <p className="mt-4 max-w-2xl text-pretty text-[15px] leading-relaxed text-muted">
          Amounts are read from SEC filings and formatted by deterministic code, not written by the
          model. Every answer shows its exact source and how it was fetched.
        </p>
      </section>

      {error && (
        <Callout kind="error" className="mb-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{error}</span>
            <Button size="sm" variant="outline" onClick={onRetry}>
              Try again
            </Button>
          </div>
        </Callout>
      )}

      <section aria-labelledby="stories-label">
        <div className="mb-3 flex items-center justify-between gap-3">
          <SectionLabel>
            <span id="stories-label">Guided stories</span>
          </SectionLabel>
          {waking && !meta && !error && (
            <span className="flex items-center gap-1.5 text-xs text-muted" role="status">
              <Loader2 className="size-3.5 animate-spin text-primary" aria-hidden />
              Waking the analysis service…
            </span>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {meta
            ? meta.guided_stories.map((story, index) => {
                const Icon = STORY_ICONS[story.label] ?? Layers;
                return (
                  <button
                    key={story.label}
                    type="button"
                    disabled={disabled}
                    onClick={() => onAsk(story.question)}
                    className="group relative flex flex-col justify-between gap-3 sm:min-h-32 sm:gap-4 overflow-hidden rounded-xl border border-border bg-surface p-4 text-left transition-[border-color,background-color,box-shadow] hover:border-primary/40 hover:shadow-[0_0_0_4px] hover:shadow-primary/5 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span
                      aria-hidden
                      className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent opacity-0 transition-opacity group-hover:opacity-100"
                    />
                    <span className="flex w-full items-center justify-between">
                      <span className="flex items-center gap-2.5">
                        <span className="flex size-8 items-center justify-center rounded-lg border border-border bg-surface-2 text-primary">
                          <Icon className="size-4" aria-hidden />
                        </span>
                        <span className="num text-[11px] text-subtle">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                      </span>
                      <ArrowUpRight
                        className="size-4 text-subtle transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
                        aria-hidden
                      />
                    </span>
                    <span>
                      <span className="block text-sm font-medium text-fg">{story.label}</span>
                      <span className="mt-1 block break-words text-[13px] leading-snug text-muted">
                        {story.question}
                      </span>
                    </span>
                  </button>
                );
              })
            : !error &&
              [0, 1, 2, 3].map((slot) => (
                <div
                  key={slot}
                  aria-hidden
                  className="flex min-h-32 flex-col justify-between rounded-xl border border-border bg-surface p-4"
                >
                  <span className="shimmer animate-shimmer size-8 rounded-lg" />
                  <span className="space-y-2">
                    <span className="shimmer animate-shimmer block h-3.5 w-2/5 rounded" />
                    <span className="shimmer animate-shimmer block h-3 w-4/5 rounded" />
                  </span>
                </div>
              ))}
        </div>
      </section>

      {meta && (
        <div className="mt-12 grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <section aria-labelledby="ask-label">
            <SectionLabel className="mb-3">
              <span id="ask-label">What you can ask</span>
            </SectionLabel>
            <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
              {meta.capabilities.map((capability) => (
                <li key={capability.description} className="px-4 py-3.5">
                  <p className="text-[13px] leading-snug text-fg">{capability.description}</p>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {capability.examples.map((example) => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => onDraft(example)}
                        title="Put this in the composer"
                        className="rounded-md border border-border bg-surface-2 px-2 py-1 text-left text-xs text-muted transition-colors hover:border-border-strong hover:text-fg"
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <section aria-labelledby="metrics-label">
            <SectionLabel className="mb-3">
              <span id="metrics-label">Supported metrics</span>
            </SectionLabel>
            <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
              {meta.metric_groups.map((group) => (
                <div key={group.title} className="px-4 py-3.5">
                  <div className="mb-2 text-xs font-medium text-muted">{group.title}</div>
                  <ul className="flex flex-wrap gap-1.5">
                    {group.names.map((name) => (
                      <li
                        key={name}
                        className="rounded-md border border-border/80 px-1.5 py-0.5 text-[11.5px] text-fg/85"
                      >
                        {name}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
