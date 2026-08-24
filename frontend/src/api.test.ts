import { afterEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "./api";

const fallback = {
  detail: "The request failed.",
  action: "Retry the request.",
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("requestJson", () => {
  it("returns a decoded successful response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ status: "ready" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      requestJson<{ status: string }>("/api/ready", fallback),
    ).resolves.toEqual({ status: "ready" });
  });

  it("normalizes a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

    await expect(requestJson("/api/ready", fallback)).rejects.toEqual({
      code: "network_error",
      detail: fallback.detail,
      action: fallback.action,
    });
  });

  it("normalizes an unreadable successful response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not-json", { status: 200 })),
    );

    await expect(requestJson("/api/ready", fallback)).rejects.toEqual({
      code: "invalid_response",
      detail: "The server returned an unreadable response.",
      action: fallback.action,
    });
  });
});
