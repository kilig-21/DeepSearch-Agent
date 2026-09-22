import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import HistoryPage from "@/app/history/page";

const report = {
  id: 7, task_id: "t_report", topic: "Python 并发方式比较", final_md: "# Python 并发方式比较\n\n已保存的正文。",
  created_at: "2026-09-22T00:00:00Z", duration_s: 65, token_cost: 1000,
  credits_cost: 2, stop_reason: "evidence_sufficient", citation_map_json: {}, sources: [], evidences: [],
};
const response = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

describe("历史报告导航", () => {
  beforeEach(() => window.history.replaceState(null, "", "/history"));
  afterEach(() => vi.unstubAllGlobals());

  it("打开报告更新地址，后退保留搜索条件，重新进入可以恢复详情", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => response(url.endsWith("/7") ? report : [report])));
    render(<HistoryPage />);
    await screen.findByRole("button", { name: /Python 并发方式比较/ });
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Python" } });
    fireEvent.click(screen.getByRole("button", { name: /Python 并发方式比较/ }));
    await screen.findByText("已保存的正文。");
    expect(window.location.search).toBe("?report=7");

    act(() => {
      window.history.replaceState(null, "", "/history");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(screen.getByRole("searchbox")).toHaveValue("Python");
    expect(screen.queryByText("已保存的正文。")).not.toBeInTheDocument();

    act(() => {
      window.history.replaceState(null, "", "/history?report=7");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await screen.findByText("已保存的正文。");
  });

  it("直达报告尚在加载时，后退到列表不会被晚到的详情覆盖", async () => {
    let resolveDetail!: (value: Response) => void;
    window.history.replaceState(null, "", "/history?report=7");
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/7")
      ? new Promise<Response>((resolve) => { resolveDetail = resolve; })
      : Promise.resolve(response([report]))));
    render(<HistoryPage />);
    await screen.findByText("正在打开报告…");
    act(() => {
      window.history.replaceState(null, "", "/history");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    await act(async () => resolveDetail(response(report)));
    await waitFor(() => expect(screen.getByRole("heading", { name: "历史报告" })).toBeInTheDocument());
    expect(screen.queryByText("已保存的正文。")).not.toBeInTheDocument();
  });
});
