import { safeHref } from "./format";
import type { DisplayTable, Presentation } from "./types";

/**
 * An answer as Markdown, for copying into a note or saving: the question, what
 * the window shows, and every source it cites, so the copy carries its own
 * provenance. Every amount is the server's string (ADR 0006); only layout is
 * added here.
 */
export function answerMarkdown(
  question: string,
  presentation: Presentation,
  /** The table's rows in the order on screen; the server's order when absent. */
  rowOrder?: number[] | null,
): string {
  const blocks: string[] = [];
  if (question.trim()) blocks.push(`## ${oneLine(question)}`);
  if (presentation.headline) blocks.push(presentation.headline);
  for (const banner of presentation.banners) blocks.push(`> ${oneLine(banner)}`);

  const card = presentation.fact_card;
  if (card) {
    const company = card.ticker ? `${card.company_name} (${card.ticker})` : card.company_name;
    const lines = [`**${card.metric_header}, ${company}: ${card.amount}**`, card.period_label];
    const filed = [card.form, card.accession_number && `accession ${card.accession_number}`].filter(Boolean);
    if (filed.length) lines.push(`Filed in ${filed.join(", ")}`);
    blocks.push(lines.filter(Boolean).join("  \n"));
  }

  for (const trend of presentation.trends ?? []) {
    const name = trend.series[0] ?? "";
    const points = trend.period_labels.map((period, index) => `${period}: ${trend.amounts[index]?.[name] ?? "—"}`);
    blocks.push(`**${trend.metric_label}, recent quarters:** ${points.join(" · ")}`);
  }

  const table = presentation.table;
  if (table && table.rows.length > 0) blocks.push(markdownTable(table, rowOrder));
  if (presentation.chart?.caption) blocks.push(`_${oneLine(presentation.chart.caption)}_`);
  if (presentation.message) blocks.push(presentation.message);
  if (presentation.essay) blocks.push(presentation.essay.trim());

  for (const change of presentation.disclosures) {
    const heading = [change.section_label, change.subsection].filter(Boolean).join(": ");
    const lines = [`### ${oneLine(heading)} (${change.change_kind})`];
    if (change.before_text) lines.push(`Before:\n${quote(change.before_text)}`);
    if (change.after_text) lines.push(`After:\n${quote(change.after_text)}`);
    blocks.push(lines.join("\n\n"));
  }

  const citations = presentation.citations.map((citation) => {
    const title = oneLine(citation.title) || citation.url;
    const link = safeHref(citation.url) ? `[${linkText(title)}](${citation.url})` : title;
    return `${citation.index}. ${link}${citation.published ? `, ${citation.published}` : ""}`;
  });
  if (citations.length) blocks.push(`**Sources**\n\n${citations.join("\n")}`);

  const filings = filingLinks(presentation);
  if (filings.length) blocks.push(`**SEC filings**\n\n${filings.join("\n")}`);
  return `${blocks.join("\n\n")}\n`;
}

/** A file name for the saved answer: the question's words, or "answer". */
export function answerFileName(question: string): string {
  const slug = question
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/, "");
  return `${slug || "answer"}.md`;
}

function markdownTable(table: DisplayTable, rowOrder?: number[] | null): string {
  const order = rowOrder ?? table.rows.map((_, index) => index);
  const line = (cells: string[]) => `| ${cells.map(cell).join(" | ")} |`;
  return [
    line(table.headers),
    line(table.headers.map(() => "---")),
    ...order.map((row) => line(table.rows[row] ?? [])),
  ].join("\n");
}

function cell(text: string): string {
  return oneLine(text).replace(/\|/g, "\\|") || " ";
}

function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** Brackets in a title would end the link early. */
function linkText(text: string): string {
  return text.replace(/[[\]]/g, "\\$&");
}

function quote(text: string): string {
  return text
    .trim()
    .split("\n")
    .map((line) => `> ${line}`.trimEnd())
    .join("\n");
}

/** Each filing the answer read, once, with what was taken from it. */
function filingLinks(presentation: Presentation): string[] {
  const seen = new Map<string, string>();
  const add = (url: string, label: string) => {
    if (!safeHref(url) || seen.has(url)) return;
    seen.set(url, oneLine(label));
  };
  // A filing is named by whose it is and its accession; several figures often share one.
  const filing = (company: string, form: string, accession: string, fallback: string) =>
    [company, [form, accession].filter(Boolean).join(" ")].filter(Boolean).join(", ") || fallback;
  const card = presentation.fact_card;
  if (card) add(card.source_url, filing(card.company_name, card.form, card.accession_number, card.metric_header));
  for (const item of presentation.evidence) {
    add(item.source_url, filing(item.company_name, item.form, item.accession_number, item.label));
  }
  for (const change of presentation.disclosures) {
    add(change.older_url, `Older filing ${change.older_accession}`);
    add(change.newer_url, `Newer filing ${change.newer_accession}`);
  }
  return [...seen].map(([url, label]) => `- [${linkText(label || url)}](${url})`);
}
