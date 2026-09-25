"use client";

import { ChevronDown, ChevronsUpDown, Route, ScanSearch } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn, parseLink, safeHref } from "@/lib/format";
import type { DisplayTrace, EvidenceItem, Pair, Presentation, QuarterlyFactCard } from "@/lib/types";
import { AnswerChart } from "./answer-chart";
import { CopyButton } from "./copy-button";
import { DataTable } from "./data-table";
import { Badge, Callout, ExternalLink, FilingButton, SectionLabel } from "./ui";

/**
 * One answer. Every amount and label here is a string from the server's
 * presentation mapping (ADR 0006); nothing is formatted in the browser.
 */
export function Answer({ presentation }: { presentation: Presentation }) {
  const { fact_card, chart, table, message, evidence, traces, banners } = presentation;
  return (
    <div className="min-w-0 space-y-4">
      <div className="flex items-center gap-2">
        <Badge tone="primary">{presentation.intent_label || presentation.intent}</Badge>
      </div>
      {banners.map((banner) => (
        <Callout key={banner} kind="info">
          {banner}
        </Callout>
      ))}
      {fact_card && <FactCard card={fact_card} />}
      {chart && <AnswerChart chart={chart} />}
      {table && table.rows.length > 0 && <DataTable table={table} />}
      {message && <Callout kind="warning">{message}</Callout>}
      {evidence.length > 0 && <EvidenceInspector items={evidence} />}
      {traces.length > 0 && <Traces traces={traces} />}
    </div>
  );
}

export function FactCard({ card }: { card: QuarterlyFactCard }) {
  return (
    <section
      aria-label={`${card.metric_header}, ${card.company_name}`}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_24px_48px_-32px_rgb(0_0_0/0.55)]"
    >
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/70 to-transparent"
      />
      <span
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-28 h-56 w-80 rounded-full bg-primary/10 blur-3xl"
      />
      <div className="relative p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="num flex h-9 min-w-9 shrink-0 items-center justify-center rounded-lg border border-border-strong bg-surface-2 px-2 text-[11px] font-semibold text-fg">
              {card.ticker}
            </span>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-fg">{card.company_name}</div>
              <div className="text-xs text-subtle">Quarterly fact</div>
            </div>
          </div>
          {card.form && <Badge className="num">{card.form}</Badge>}
        </div>
        <div className="mt-7">
          <SectionLabel>{card.metric_header}</SectionLabel>
          <div className="figure mt-2 text-[44px] font-semibold leading-none text-fg sm:text-[60px]">
            {card.amount}
          </div>
          <div className="mt-3 text-[13px] text-muted">{card.period_label}</div>
        </div>
      </div>
      <div className="relative grid border-t border-border bg-surface-2/50 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto]">
        {card.accession_number && (
          <FactField label="Accession number">
            <span className="num truncate">{card.accession_number}</span>
            <CopyButton value={card.accession_number} label="accession number" />
          </FactField>
        )}
        {card.concept && (
          <FactField label="Concept">
            <span className="num truncate" title={card.concept}>
              {card.concept}
            </span>
          </FactField>
        )}
        {safeHref(card.source_url) && (
          <div className="flex items-center border-t border-border px-5 py-3 sm:border-l sm:border-t-0 sm:px-4">
            <FilingButton href={card.source_url} emphasis />
          </div>
        )}
      </div>
    </section>
  );
}

function FactField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 border-border px-5 py-3 [&+&]:border-t sm:[&+&]:border-l sm:[&+&]:border-t-0 sm:px-4 sm:first:pl-6">
      <div className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">{label}</div>
      <div className="mt-1 flex min-w-0 items-center gap-1 text-[13px] text-fg">{children}</div>
    </div>
  );
}

export function EvidenceInspector({ items }: { items: EvidenceItem[] }) {
  const [chosen, setChosen] = useState(0);
  const selectId = useId();
  const item = items[Math.min(chosen, items.length - 1)];
  const company = [item.company_name, item.ticker].filter(Boolean).join(" · ");
  return (
    <section
      aria-label="Evidence inspector"
      className="overflow-hidden rounded-xl border border-border bg-surface"
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2 text-[13px] font-medium text-fg">
          <ScanSearch className="size-4 text-primary" aria-hidden />
          Inspect exact source
        </div>
        <span className="num text-[11px] text-subtle">
          {items.length === 1 ? "1 source" : `${chosen + 1} of ${items.length} sources`}
        </span>
      </header>
      {items.length > 1 && (
        <div className="relative border-b border-border px-4 py-2.5">
          <label htmlFor={selectId} className="sr-only">
            Evidence item
          </label>
          <select
            id={selectId}
            value={chosen}
            onChange={(event) => setChosen(Number(event.target.value))}
            className="h-8 w-full appearance-none truncate rounded-lg border border-border bg-surface-2 pl-2.5 pr-8 text-[13px] text-fg outline-none hover:border-border-strong focus-visible:border-primary"
          >
            {items.map((option, index) => (
              <option key={`${option.label}-${index}`} value={index}>
                {index + 1}. {option.label}
              </option>
            ))}
          </select>
          <ChevronsUpDown
            className="pointer-events-none absolute right-6 top-1/2 size-3.5 -translate-y-1/2 text-subtle"
            aria-hidden
          />
        </div>
      )}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3.5 px-4 py-4">
        <EvidenceField pair label="Amount">
          <span className="figure text-xl font-semibold text-fg">{item.amount}</span>
        </EvidenceField>
        <EvidenceField pair label="Exact amount" hidden={!item.raw_amount}>
          <code className="num rounded-md border border-border bg-surface-2 px-1.5 py-0.5 text-[12.5px] text-fg">
            {item.raw_amount}
          </code>
        </EvidenceField>
        <EvidenceField label="Company" hidden={!company}>
          {company}
        </EvidenceField>
        <EvidenceField label="Period" hidden={!item.period_label}>
          {item.period_label}
        </EvidenceField>
        <EvidenceField pair label="CIK" hidden={!item.cik}>
          <span className="num">{item.cik}</span>
          <CopyButton value={item.cik} label="CIK" />
        </EvidenceField>
        <EvidenceField pair label="Form" hidden={!item.form}>
          <span className="num">{item.form}</span>
        </EvidenceField>
        <EvidenceField label="Accession number" hidden={!item.accession_number}>
          <span className="num">{item.accession_number}</span>
          <CopyButton value={item.accession_number} label="accession number" />
        </EvidenceField>
        <EvidenceField label="Concept" hidden={!item.concept}>
          <span className="num break-all">{item.concept}</span>
        </EvidenceField>
        <EvidenceField label="Selection rule" hidden={!item.selection_rule} wide>
          <span className="text-muted">{item.selection_rule}</span>
        </EvidenceField>
      </dl>
      {safeHref(item.source_url) && (
        <footer className="flex justify-end border-t border-border bg-surface-2/40 px-4 py-2.5">
          <FilingButton href={item.source_url} />
        </footer>
      )}
    </section>
  );
}

function EvidenceField({
  label,
  hidden = false,
  wide = false,
  pair = false,
  children,
}: {
  label: string;
  hidden?: boolean;
  /** Spans both columns at every width. */
  wide?: boolean;
  /** Short enough to sit beside its neighbour even on a phone. */
  pair?: boolean;
  children: ReactNode;
}) {
  if (hidden) return null;
  return (
    <div className={cn("min-w-0", wide ? "col-span-2" : pair ? "col-span-1" : "col-span-2 sm:col-span-1")}>
      <dt className="text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">{label}</dt>
      <dd className="mt-1 flex min-w-0 items-center gap-1 text-[13px] text-fg">{children}</dd>
    </div>
  );
}

export function Traces({ traces }: { traces: DisplayTrace[] }) {
  return (
    <section aria-label="How this answer was fetched">
      <SectionLabel className="mb-2">How this answer was fetched</SectionLabel>
      <div className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface">
        {traces.map((trace, index) => (
          <details key={`${trace.header}-${index}`} className="group">
            <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 text-[13px] transition-colors hover:bg-surface-2/60 [&::-webkit-details-marker]:hidden">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
                <Route className="size-3.5" aria-hidden />
              </span>
              <span className="min-w-0 flex-1 text-fg">{trace.header}</span>
              <ChevronDown
                className="size-4 shrink-0 text-subtle transition-transform group-open:rotate-180"
                aria-hidden
              />
            </summary>
            <div className="grid gap-5 border-t border-border bg-surface-2/35 px-4 py-4 md:grid-cols-2">
              {trace.inputs.length > 0 && <TraceGroup title="Request" fields={trace.inputs} />}
              {trace.outputs.length > 0 && <TraceGroup title="Result" fields={trace.outputs} />}
            </div>
          </details>
        ))}
      </div>
    </section>
  );
}

function TraceGroup({ title, fields }: { title: string; fields: Pair[] }) {
  return (
    <div className="min-w-0">
      <div className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.08em] text-subtle">
        {title}
      </div>
      <dl className="grid grid-cols-[minmax(6.5rem,auto)_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[12.5px]">
        {fields.map(([label, value], index) => (
          <TraceRow key={`${label}-${index}`} label={label} value={value} />
        ))}
      </dl>
    </div>
  );
}

function TraceRow({ label, value }: { label: string; value: string }) {
  if (!value) {
    if (!label) return <div aria-hidden className="col-span-2 h-2" />;
    return <dt className="col-span-2 mt-1 font-medium text-fg">{label}</dt>;
  }
  if (value.includes("\n")) {
    return (
      <div className="col-span-2 min-w-0">
        {label && <dt className="mb-1 font-medium text-fg">{label}</dt>}
        <dd className="prose-answer text-[12.5px] text-muted">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: MarkdownLink }}>
            {value}
          </ReactMarkdown>
        </dd>
      </div>
    );
  }
  const link = parseLink(value);
  return (
    <>
      <dt className="text-subtle">{label}</dt>
      <dd className="min-w-0 break-words text-fg">
        {link ? (
          <ExternalLink href={link.href} className="break-all">
            {link.text}
          </ExternalLink>
        ) : (
          value
        )}
      </dd>
    </>
  );
}

function MarkdownLink({ href, children }: { href?: string; children?: ReactNode }) {
  if (!href || !safeHref(href)) return <>{children}</>;
  return (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  );
}
