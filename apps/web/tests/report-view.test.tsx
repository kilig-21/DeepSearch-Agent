// ReportView 组件测试(第四轮评审 F1;测试类7:Markdown 实际渲染三路径
// + 远程图片零网络请求)
// - 普通 Markdown 正常渲染, [n] 构造真实 URL 链接(F3)
// - 危险 HTML(script/事件属性)被剔除
// - img(语法与 raw HTML)全部剔除, 不产生任何网络请求
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportView } from "@/components/research/report-view";

describe("ReportView", () => {
  beforeEach(() => {
    // 零网络请求哨兵:渲染过程中任何 fetch 都算失败
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network"));
  });

  it("普通 Markdown 渲染:标题/段落/[n]→真实 URL 链接", () => {
    const { container } = render(
      <ReportView
        markdown={"# 研究标题\n\n正文有依据 [1],再来一点 [1][2]。\n"}
        citationUrls={{
          "1": "https://real.example/a",
          "2": "https://real.example/b",
        }}
      />,
    );
    expect(container.querySelector("h1")).toHaveTextContent("研究标题");
    const links = Array.from(container.querySelectorAll("a"));
    // 正文 3 处 [n] 链接 + 引用来源表 2 条 = 5;href 全部为真实 URL
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://real.example/a",
      "https://real.example/a",
      "https://real.example/b",
      "https://real.example/a",   // 引用来源表
      "https://real.example/b",
    ]);
    // 引用来源表列出真实 URL
    expect(screen.getByText("https://real.example/a")).toBeInTheDocument();
  });

  it("危险 HTML 被剔除:script 与事件属性不得出现在 DOM", () => {
    const { container } = render(
      <ReportView
        markdown={
          '段落<script>alert(1)</script>与<span onclick="alert(1)">点</span>以及' +
          '[1](javascript:alert(1))'
        }
        citationUrls={{}}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).not.toContain("onerror");
    expect(container.innerHTML).not.toContain("onclick");
    // javascript: 协议被 sanitize 拦截, 链接不成立(href 被整个移除)
    const links = Array.from(container.querySelectorAll("a"));
    for (const a of links) {
      const href = a.getAttribute("href");
      expect(href === null || !/^javascript:/i.test(href)).toBe(true);
    }
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("img 三条路径全部剔除且零网络请求(远程图片不加载)", () => {
    const { container } = render(
      <ReportView
        markdown={
          "![](https://evil.example/track.png)\n\n" +
          '<img src="https://evil.example/x.png" onerror="fetch(\'https://evil.example\')">\n\n' +
          "正文 [1]。"
        }
        citationUrls={{}}
      />,
    );
    // Markdown 图片语法与 raw img 均不得成为 DOM 节点
    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toContain("<img");
    expect(container.innerHTML).not.toContain("onerror");
    // 正文文本不受影响
    expect(container.textContent).toContain("正文 [1]。");
    // 零网络请求: 无 img 节点即无资源加载; fetch 哨兵未被触发
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
