import { ArrowRight, FileDiff } from "lucide-react";
import { cn } from "@/lib/format";
import type { DisplayDisclosure } from "@/lib/types";
import { SafeMarkdown } from "./markdown";
import { Badge, FilingButton, SectionLabel, type Tone } from "./ui";

const KIND_TONE: Record<string, Tone> = {
  added: "positive",
  removed: "negative",
  changed: "warning",
};

/** Each changed 10-Q section, previous and current text side by side (stacked on phones). */
export function FilingChanges({ items }: { items: DisplayDisclosure[] }) {
  const { older_accession: older, newer_accession: newer } = items[0];
  return (
    <section aria-label="Filing changes" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <SectionLabel>
          {items.length === 1 ? "1 section changed" : `${items.length} sections changed`}
        </SectionLabel>
        {older && newer && (
          <div className="num flex items-center gap-1.5 text-[11px] text-subtle">
            <span>{older}</span>
            <ArrowRight className="size-3 shrink-0" aria-label="to" />
            <span className="text-muted">{newer}</span>
          </div>
        )}
      </div>
      {items.map((item, index) => (
        <FilingChange key={`${item.section_label}-${index}`} item={item} />
      ))}
    </section>
  );
}

function FilingChange({ item }: { item: DisplayDisclosure }) {
  return (
    <article
      aria-label={`${item.section_label}, ${item.change_kind}`}
      className="overflow-hidden rounded-xl border border-border bg-surface"
    >
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-2.5 sm:px-5">
        <h3 className="flex min-w-0 items-start gap-2 text-[13px] font-medium leading-snug text-fg">
          <FileDiff className="mt-px size-4 shrink-0 text-primary" aria-hidden />
          <span className="min-w-0 text-pretty">{item.section_label}</span>
        </h3>
        <Badge tone={KIND_TONE[item.change_kind] ?? "neutral"} className="shrink-0 capitalize">
          {item.change_kind}
        </Badge>
      </header>
      <div className="grid md:grid-cols-2">
        <FilingSide
          label="Previous filing"
          text={item.before_text}
          href={item.older_url}
          link="Open previous filing"
        />
        <FilingSide
          current
          label="Current filing"
          text={item.after_text}
          href={item.newer_url}
          link="Open current filing"
        />
      </div>
    </article>
  );
}

function FilingSide({
  label,
  text,
  href,
  link,
  current = false,
}: {
  label: string;
  text: string;
  href: string;
  link: string;
  current?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col border-border",
        current ? "border-t md:border-l md:border-t-0" : "bg-surface-2/35",
      )}
    >
      <div className="px-4 pt-3.5 sm:px-5">
        <div className="flex items-center gap-2 text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">
          <span
            aria-hidden
            className={cn(
              "size-1.5 rounded-full",
              current ? "bg-primary shadow-[0_0_0_3px] shadow-primary/15" : "bg-subtle/60",
            )}
          />
          {label}
        </div>
      </div>
      <div className="flex-1 px-4 py-3 sm:px-5">
        {text ? (
          <SafeMarkdown text={text} className={cn("text-[14px]", !current && "text-muted")} />
        ) : (
          <p className="text-[13px] italic text-subtle">Not in this filing.</p>
        )}
      </div>
      <div className="px-4 pb-4 sm:px-5">
        <FilingButton href={href} label={link} emphasis={current} />
      </div>
    </div>
  );
}
