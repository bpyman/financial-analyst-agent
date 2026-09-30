import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { citationIndex, linkCitations } from "../lib/essay";
import { cn, safeHref } from "../lib/format";

export interface MarkdownCitation {
  index: number;
  title: string;
  url: string;
}

/**
 * Model- or filing-written markdown. Raw HTML is dropped, images draw as their
 * alt text, and only http(s) links render as links; anything else stays text.
 * [n] markers become chips linking to the matching citation. With
 * `citedLinksOnly`, a link to anything but a cited source stays text: a model's
 * essay must not carry a link a news snippet talked it into.
 */
export function SafeMarkdown({
  text,
  citations = [],
  citedLinksOnly = false,
  className,
}: {
  text: string;
  citations?: MarkdownCitation[];
  citedLinksOnly?: boolean;
  className?: string;
}) {
  const components: Components = {
    a: ({ href, children }) => (
      <MarkdownLink href={href} citations={citations} citedLinksOnly={citedLinksOnly}>
        {children}
      </MarkdownLink>
    ),
    img: ({ alt }) => (alt ? <span>{alt}</span> : null),
  };
  return (
    <div className={cn("prose-answer", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {linkCitations(text, citations.length)}
      </ReactMarkdown>
    </div>
  );
}

function MarkdownLink({
  href,
  citations,
  citedLinksOnly,
  children,
}: {
  href?: string;
  citations: MarkdownCitation[];
  citedLinksOnly: boolean;
  children?: ReactNode;
}) {
  const cited = href ? citationIndex(href) : null;
  if (cited !== null) {
    const source = citations.find((citation) => citation.index === cited);
    if (!source || !safeHref(source.url)) return <>[{cited}]</>;
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noreferrer noopener"
        className="cite"
        aria-label={`Source ${cited}: ${source.title}`}
        title={source.title}
      >
        {cited}
      </a>
    );
  }
  if (!href || !safeHref(href)) return <>{children}</>;
  if (citedLinksOnly && !citations.some((citation) => citation.url === href)) return <>{children}</>;
  return (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  );
}
