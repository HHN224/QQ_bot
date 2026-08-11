// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

const digest = {
  digest_date: "2026-08-11",
  generated_at: "2026-08-11T08:00:00Z",
  stats: { total: 1, must_read: 1, interesting: 0, categories: { "工具": 1 }, model_mode: "cloud" },
  items: [{
    id: 42,
    section: "must_read",
    rank: 1,
    category: "工具",
    conclusion: "值得关注的开源工具",
    why_read: "可以提高调试效率",
    context_summary: "这是上下文摘要。",
    source_excerpt: "群友分享了一个开源工具。",
    source_time: "09:31",
    source_author: "张三",
    links: [],
    credibility: "unverified",
  }],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("digest feedback", () => {
  it("shows a selected state after useful feedback is saved", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/feedback" && init?.method === "POST") {
        return new Response(null, { status: 204 });
      }
      return new Response(JSON.stringify(digest), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /今日简报/ }));
    expect(await screen.findByText("值得关注的开源工具")).toBeTruthy();

    const useful = screen.getByRole("button", { name: "有用" });
    await userEvent.click(useful);

    expect(useful.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("已记录，感谢反馈")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/feedback",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows a retryable error when feedback cannot be saved", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/feedback" && init?.method === "POST") {
        return new Response(JSON.stringify({ detail: "failed" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify(digest), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /今日简报/ }));
    expect(await screen.findByText("值得关注的开源工具")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "没用" }));

    expect(await screen.findByText("保存失败，请重试")).toBeTruthy();
    expect(screen.getByRole("button", { name: "没用" }).getAttribute("aria-pressed")).toBe("false");
  });
});
