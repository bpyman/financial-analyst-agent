// Mirrors financial_analyst_agent.presentation dataclasses as serialised by
// financial_analyst_agent.api. tests/test_api.py pins the key set.

export type Pair = [label: string, value: string];

export interface QuarterlyFactCard {
  company_name: string;
  ticker: string;
  metric_header: string;
  amount: string;
  period_label: string;
  form: string;
  accession_number: string;
  concept: string;
  source_url: string;
}

export interface DisplayTable {
  headers: string[];
  keys: string[];
  rows: string[][];
  numbers: (number | null)[][];
}

export interface DisplayTrace {
  header: string;
  inputs: Pair[];
  outputs: Pair[];
}

export interface DisplayCitation {
  index: number;
  title: string;
  url: string;
  published: string | null;
}

export type ValueKind = "usd" | "percent" | "multiple";

interface ChartBase {
  title: string;
  metric: string;
  metric_label: string;
  value_kind: ValueKind;
  caption: string;
  horizontal: boolean;
}

export interface BarRecord {
  Company: string;
  Value: number;
  Amount: string;
  Label: string;
  Missing: boolean;
  Period?: string;
}

export interface BarChartSpec extends ChartBase {
  kind: "bar";
  records: BarRecord[];
}

export interface LineChartSpec extends ChartBase {
  kind: "line";
  records: Record<string, string | number | null>[];
  period_labels: string[];
  series: string[];
  amounts: Record<string, string>[];
}

export type ChartSpec = BarChartSpec | LineChartSpec;

export interface EvidenceItem {
  label: string;
  amount: string;
  raw_amount: string;
  company_name: string;
  ticker: string;
  cik: string;
  concept: string;
  period_label: string;
  accession_number: string;
  form: string;
  source_url: string;
  selection_rule: string;
}

export interface DisplayDisclosure {
  section_label: string;
  change_kind: string;
  before_text: string;
  after_text: string;
  older_accession: string;
  newer_accession: string;
  older_url: string;
  newer_url: string;
}

export interface Presentation {
  intent: string;
  intent_label: string;
  banners: string[];
  traces: DisplayTrace[];
  citations: DisplayCitation[];
  fact_card: QuarterlyFactCard | null;
  table: DisplayTable | null;
  chart: ChartSpec | null;
  evidence: EvidenceItem[];
  disclosures: DisplayDisclosure[];
  essay: string | null;
  message: string | null;
  candidates: string[];
}

export interface Turn {
  index: number;
  message: string;
  presentation: Presentation;
  candidate_slugs: string[];
  clarify_enabled: boolean;
}

/** The provider set a thread is bound to for its whole life. */
export type RuntimeKind = "recorded" | "live";

/** POST /api/threads. `notice` is set when the deployment served another runtime. */
export interface CreatedThread {
  thread_id: string;
  runtime: RuntimeKind;
  notice: string | null;
}

export interface ThreadView {
  thread_id: string;
  /** null until the thread is bound (a thread saved before binding existed). */
  runtime: RuntimeKind | null;
  turns: Turn[];
  spec_chips: string[];
  pending_clarification: boolean;
  turn_count: number;
  max_turns: number;
}

export interface Meta {
  recorded: { default: boolean; locked: boolean };
  /** Status-line copy per runtime, and the tooltip for a locked runtime switch. */
  runtime_copy: { recorded: string; live: string; locked: string };
  snapshot: { banner: string; stale: boolean };
  example_query: string;
  guided_stories: { label: string; question: string }[];
  capabilities: { description: string; examples: string[] }[];
  metric_groups: { title: string; names: string[] }[];
  max_message_chars: number;
}

export type TurnEvent =
  | { event: "progress"; data: { done: number; total: number } }
  | { event: "thread"; data: ThreadView }
  | { event: "error"; data: { message: string } };
