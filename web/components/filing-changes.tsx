import { ArrowRight, ChevronDown, FileDiff } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/format";
import type { DisplayDisclosure } from "@/lib/types";
import { Badge, FilingButton, SectionLabel, type Tone } from "./ui";

const KIND_TONE: Record<string, Tone> = {
  added: "positive",
  removed: "negative",
  changed: "warning",
};

// Changes shown per section before "Show more": a 10-Q pair can differ in a hundred paragraphs.
const FIRST_CHANGES = 3;

/** Each changed 10-Q section, previous and current text side by side (stacked on phones). */
export function FilingChanges({ items }: { items: DisplayDisclosure[] }) {
  const { older_accession: older, newer_accession: newer } = items[0];
  // Each item is one changed paragraph; several can sit in one section.
  const sections = groupBySection(items);
  return (
    <section aria-label="Filing changes" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5">
        <SectionLabel>
          {`${items.length} ${items.length === 1 ? "change" : "changes"} in ${sections.length} ${
            sections.length === 1 ? "section" : "sections"
          }`}
        </SectionLabel>
        {older && newer && (
          <div className="num flex items-center gap-1.5 text-[11px] text-subtle">
            <span>{older}</span>
            <ArrowRight className="size-3 shrink-0" aria-label="to" />
            <span className="text-muted">{newer}</span>
          </div>
        )}
      </div>
      {sections.map(([label, changes]) => (
        <FilingSection key={label} label={label} changes={changes} />
      ))}
    </section>
  );
}

function groupBySection(items: DisplayDisclosure[]): [string, DisplayDisclosure[]][] {
  const sections = new Map<string, DisplayDisclosure[]>();
  for (const item of items) {
    sections.set(item.section_label, [...(sections.get(item.section_label) ?? []), item]);
  }
  return [...sections];
}

function FilingSection({ label, changes }: { label: string; changes: DisplayDisclosure[] }) {
  const [open, setOpen] = useState(false);
  const shown = open ? changes : changes.slice(0, FIRST_CHANGES);
  const hidden = changes.length - shown.length;
  return (
    <div className="space-y-3">
      {shown.map((item, index) => (
        <FilingChange key={index} item={item} />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex w-full items-center justify-center gap-1.5 rounded-xl border border-dashed border-border-strong px-4 py-2.5 text-xs font-medium text-muted transition-colors hover:border-primary/50 hover:bg-primary-soft hover:text-fg"
        >
          <ChevronDown className="size-3.5" aria-hidden />
          {`Show ${hidden} more ${hidden === 1 ? "change" : "changes"} in ${label}`}
        </button>
      )}
    </div>
  );
}

// Characters either side may run to before the pair is clamped with "Show full text".
const LONG_CHANGE = 1200;

function FilingChange({ item }: { item: DisplayDisclosure }) {
  const long = Math.max(item.before_text.length, item.after_text.length) > LONG_CHANGE;
  const [expanded, setExpanded] = useState(false);
  const clamped = long && !expanded;
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
          clamped={clamped}
        />
        <FilingSide
          current
          label="Current filing"
          text={item.after_text}
          href={item.newer_url}
          link="Open current filing"
          clamped={clamped}
        />
      </div>
      {long && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((open) => !open)}
          className="flex w-full items-center justify-center gap-1.5 border-t border-border px-4 py-2 text-xs font-medium text-muted transition-colors hover:bg-surface-2 hover:text-fg"
        >
          <ChevronDown className={cn("size-3.5 transition-transform", expanded && "rotate-180")} aria-hidden />
          {expanded ? "Show less" : "Show full text"}
        </button>
      )}
    </article>
  );
}

function FilingSide({
  label,
  text,
  href,
  link,
  current = false,
  clamped = false,
}: {
  label: string;
  text: string;
  href: string;
  link: string;
  current?: boolean;
  /** Long text is cut to a fixed height, fading out, until the reader expands it. */
  clamped?: boolean;
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
      <div
        className={cn(
          "flex-1 px-4 py-3 sm:px-5",
          clamped &&
            "max-h-[22rem] overflow-hidden [mask-image:linear-gradient(to_bottom,black_75%,transparent)]",
        )}
      >
        {text ? (
          // Filing prose, as filed: "1." or "*" in a 10-Q is not markup.
          <p className={cn("whitespace-pre-wrap break-words text-[14px] leading-[1.7] text-fg", !current && "text-muted")}>
            {text}
          </p>
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
