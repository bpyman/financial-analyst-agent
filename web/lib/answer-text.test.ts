import { describe, expect, it } from "vitest";
import { answerFileName, answerMarkdown } from "./answer-text";
import type { Presentation } from "./types";

const EMPTY: Presentation = {
  intent: "compare",
  intent_label: "Comparison",
  banners: [],
  traces: [],
  citations: [],
  fact_card: null,
  table: null,
  chart: null,
  evidence: [],
  disclosures: [],
  essay: null,
  message: null,
  candidates: [],
  clarify_prompt: null,
  suggestions: [],
  message_tone: "info",
  headline: null,
};

const FILING = "https://www.sec.gov/Archives/edgar/data/59478/000005947826000012/0000059478-26-000012-index.htm";

describe("answerMarkdown", () => {
  it("lays out the question, the table in its sorted order, and each filing once", () => {
    const text = answerMarkdown(
      "Compare net margin for Lilly and Merck",
      {
        ...EMPTY,
        headline: "Eli Lilly's net margin was higher.",
        banners: ["Figures are from each company's latest 10-Q."],
        table: {
          headers: ["Company", "Net margin"],
          keys: ["company_name", "value:net_margin"],
          rows: [
            ["Merck | Co", "21.1%"],
            ["Eli Lilly", "31.4%"],
          ],
          numbers: [
            [null, 0.211],
            [null, 0.314],
          ],
        },
        evidence: [
          { ...evidence(), label: "Net income" },
          { ...evidence(), label: "Revenue" },
        ],
      },
      [1, 0],
    );
    expect(text).toBe(
      [
        "## Compare net margin for Lilly and Merck",
        "Eli Lilly's net margin was higher.",
        "> Figures are from each company's latest 10-Q.",
        "| Company | Net margin |\n| --- | --- |\n| Eli Lilly | 31.4% |\n| Merck \\| Co | 21.1% |",
        `**SEC filings**\n\n- [Eli Lilly and Company, 10-Q 0000059478-26-000012](${FILING})`,
      ].join("\n\n") + "\n",
    );
  });

  it("numbers the essay's sources and quotes a changed paragraph", () => {
    const text = answerMarkdown("What changed?", {
      ...EMPTY,
      essay: "Risk rose [1].",
      citations: [
        { index: 1, title: "Q2 [call] notes", url: "https://example.com/a", published: "Jul 1, 2026" },
        { index: 2, title: "Unsafe", url: "javascript:alert(1)", published: null },
      ],
      disclosures: [
        {
          section_label: "Risk Factors",
          subsection: "Supply Chain",
          change_kind: "changed",
          before_text: "We may face delays.",
          after_text: "We could face delays.\nAnd costs.",
          older_accession: "A-1",
          newer_accession: "A-2",
          older_url: "https://www.sec.gov/a1",
          newer_url: "https://www.sec.gov/a2",
        },
      ],
    });
    expect(text).toContain("### Risk Factors: Supply Chain (changed)");
    expect(text).toContain("After:\n> We could face delays.\n> And costs.");
    expect(text).toContain("1. [Q2 \\[call\\] notes](https://example.com/a), Jul 1, 2026\n2. Unsafe");
    expect(text).toContain("- [Older filing A-1](https://www.sec.gov/a1)\n- [Newer filing A-2](https://www.sec.gov/a2)");
  });

  it("lists an overview's recent quarters, which the table does not hold", () => {
    const text = answerMarkdown("How is Nvidia doing?", {
      ...EMPTY,
      trends: [
        {
          kind: "line",
          title: "Trend",
          metric: "revenue",
          metric_label: "Revenue",
          value_kind: "usd",
          caption: "",
          horizontal: false,
          records: [],
          period_labels: ["Apr 26, 2026", "Jul 26, 2026"],
          series: ["NVIDIA Corporation"],
          amounts: [{ "NVIDIA Corporation": "$81.62 B" }, { "NVIDIA Corporation": "$96.22 B" }],
        },
      ],
    });
    expect(text).toContain("**Revenue, recent quarters:** Apr 26, 2026: $81.62 B · Jul 26, 2026: $96.22 B");
  });
});

describe("answerFileName", () => {
  it("names the file after the question", () => {
    expect(answerFileName("How is NVIDIA doing?")).toBe("how-is-nvidia-doing.md");
    expect(answerFileName("???")).toBe("answer.md");
  });
});

function evidence() {
  return {
    label: "",
    amount: "$1.00 B",
    raw_amount: "1000000000",
    company_name: "Eli Lilly and Company",
    ticker: "LLY",
    cik: "59478",
    concept: "us-gaap:NetIncomeLoss",
    period_label: "Jun 30, 2026",
    accession_number: "0000059478-26-000012",
    form: "10-Q",
    source_url: FILING,
    selection_rule: "",
  };
}
