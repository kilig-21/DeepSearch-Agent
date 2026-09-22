"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: (defaultSchema.tagNames ?? []).filter((tag) => tag !== "img"),
};

type MarkdownNode = {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
};

function safeSourceUrl(value: string) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? value : undefined;
  } catch {
    return undefined;
  }
}

// Transform citation text, while preserving code and existing Markdown links.
// Construct link nodes so source URLs are never interpreted as Markdown syntax.
function remarkCitations(urls: Record<string, string>) {
  return (tree: MarkdownNode) => {
    const visit = (node: MarkdownNode) => {
      if (!node.children || ["link", "linkReference", "code", "inlineCode"].includes(node.type)) return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== "text" || !child.value) {
          visit(child);
          return [child];
        }
        const parts: MarkdownNode[] = [];
        let offset = 0;
        for (const match of child.value.matchAll(/\[(\d+)\]/g)) {
          const url = safeSourceUrl(urls[match[1]] ?? "");
          if (!url) continue;
          if (match.index > offset) parts.push({ type: "text", value: child.value.slice(offset, match.index) });
          parts.push({ type: "link", url, children: [{ type: "text", value: `[${match[1]}]` }] });
          offset = match.index + match[0].length;
        }
        if (!parts.length) return [child];
        if (offset < child.value.length) parts.push({ type: "text", value: child.value.slice(offset) });
        return parts;
      });
    };
    visit(tree);
  };
}

export function ReportView({
  markdown,
  citationUrls,
  sources = [],
  title,
  copyable = true,
}: {
  markdown: string;
  citationUrls: Record<string, string>;
  sources?: { url: string; title: string }[];
  title?: string;
  copyable?: boolean;
}) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  if (!markdown) return null;
  const cited = Object.entries(citationUrls)
    .filter(([, url]) => safeSourceUrl(url))
    .sort(([a], [b]) => Number(a) - Number(b));
  const sourceTitles = new Map(sources.map((source) => [source.url, source.title]));

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopyState("idle"), 3000);
  };

  return (
    <article className="report-reader">
      {title || copyable ? <div className="reader-heading">
        {title ? <h2>{title}</h2> : <span>研究报告</span>}
        {copyable ? <button type="button" className="reader-copy" onClick={() => void copy()} aria-label="复制 Markdown 正文">
          {copyState === "copied" ? "已复制" : "复制正文"}
        </button> : null}
      </div> : null}
      <span className="reader-copy-status" role="status">{copyState === "copied" ? "正文已复制" : copyState === "failed" ? "无法访问剪贴板，请选择正文手动复制。" : ""}</span>
      <div className="report-prose">
        <ReactMarkdown
          remarkPlugins={[remarkGfm, [remarkCitations, citationUrls]]}
          rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
          components={{
            a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
            table: ({ children }) => <div className="report-table-scroll" role="region" aria-label="报告表格，可横向滚动" tabIndex={0}><table>{children}</table></div>,
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>
      {cited.length > 0 ? <section className="citation-section" aria-label="引用来源">
        <div className="citation-heading"><h3>引用来源</h3><span>{cited.length} 条引用</span></div>
        <ol className="citation-list">
          {cited.map(([number, url]) => <li key={number}>
            <span className="citation-number">[{number}]</span>
            <a href={url} target="_blank" rel="noopener noreferrer">
              <strong>{sourceTitles.get(url) || new URL(url).hostname}</strong>
              <span>{url}</span>
            </a>
            <span className="citation-arrow" aria-hidden="true">↗</span>
          </li>)}
        </ol>
      </section> : null}
    </article>
  );
}
