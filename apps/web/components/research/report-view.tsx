"use client";

// 报告渲染(计划书 §7;第四轮评审 F1/F3):
// - Markdown 过 rehype-sanitize:schema 基于 defaultSchema 改写(禁脚本/
//   事件属性, tagNames 剔除 img → 远程图片零网络请求)
// - 引用 [n] 预处理为 [n](真实 URL)链接。citationUrls 由 hook 经详情
//   数据 evidences.source_id → sources 联查得到;绝不把 evidence_id 当 href。
//   citationUrls 缺失的编号保持纯文本(草稿阶段)
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

// F1:schema 传参修正 —— tagNames 是字符串允许列表(不是 {img: null} 对象),
// 类型错误曾导致渲染抛 TypeError。默认 schema 允许 img, 显式剔除。
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: (defaultSchema.tagNames ?? []).filter((tag) => tag !== "img"),
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), "target", "rel"],
  },
};

export function ReportView({
  markdown,
  citationUrls,
  title,
}: {
  markdown: string;
  citationUrls: Record<string, string>;
  title?: string;
}) {
  if (!markdown) return null;

  // [1] / [1][2] → [1](url)。仅替换尚未带链接的引用标记;真实 URL
  // 联查不到的编号保持纯文本, 不伪造链接。
  const withLinks = markdown.replace(
    /\[(\d{1,2})\](?!\()/g,
    (m, n: string) => {
      const url = citationUrls[n];
      return url ? `[${n}](${url})` : m;
    },
  );

  const cited = Object.entries(citationUrls);

  return (
    <div className="space-y-4">
      {title ? <h2 className="text-xl font-semibold">{title}</h2> : null}
      <div className="max-w-none break-words text-sm leading-6 [&_h1]:mb-2 [&_h1]:mt-4 [&_h1]:text-lg [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-base [&_h2]:font-bold [&_h3]:mb-1 [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_ol_li]:ml-6 [&_ol_li]:list-decimal [&_p]:my-2 [&_table]:my-2 [&_table]:w-full [&_th]:border [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_blockquote]:border-l-4 [&_blockquote]:border-gray-300 [&_blockquote]:pl-3 [&_blockquote]:text-gray-600 [&_code]:rounded [&_code]:bg-gray-100 [&_code]:px-1">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
          components={{
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ),
          }}
        >
          {withLinks}
        </ReactMarkdown>
      </div>
      {cited.length > 0 ? (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-gray-700">引用来源</h3>
          <ol className="list-decimal space-y-0.5 pl-5 text-xs">
            {cited.map(([n, url]) => (
              <li key={n} className="break-all">
                <span className="mr-1 font-medium">[{n}]</span>
                <a
                  className="text-blue-600 hover:underline"
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {url}
                </a>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}
