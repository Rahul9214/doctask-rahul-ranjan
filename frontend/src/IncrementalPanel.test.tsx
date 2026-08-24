import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import IncrementalPanel from "./IncrementalPanel";

function jsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("IncrementalPanel", () => {
  it("renders recorded focused-update measurements without inventing values", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          jsonResponse({
            run_id: "incremental-1",
            status: "completed",
            change_kind: "source_changed",
            evidence: {
              full_rerun: false,
              classify_skipped_source_version_ids: [
                "version-1",
                "version-2",
                "version-3",
              ],
            },
            measurement: {
              changed_source_count: 1,
              affected_fact_count: 2,
              reused_fact_count: 7,
              affected_contradiction_count: 1,
              incremental_understand_model_operations: 2,
              avoided_model_operations: 3,
              duration_ms: 432,
            },
            artifacts: [{ artifact_kind: "fact" }],
          }),
        ),
      ),
    );

    render(<IncrementalPanel corpora={[]} />);
    await user.click(screen.getByText("Technical lookup"));
    await user.type(screen.getByLabelText("Corpus"), "corpus-1");
    await user.type(
      screen.getByLabelText("Incremental run ID"),
      "incremental-1",
    );
    await user.click(
      screen.getByRole("button", { name: "Load update evidence" }),
    );

    expect(await screen.findByText("Source Changed")).toBeInTheDocument();
    expect(screen.getByText("Changed sources").nextSibling).toHaveTextContent(
      "1",
    );
    expect(
      screen.getByText("Unchanged sources skipped").nextSibling,
    ).toHaveTextContent("3");
    expect(screen.getByText("Facts reused").nextSibling).toHaveTextContent("7");
    expect(screen.getByText("Full rerun").nextSibling).toHaveTextContent("No");
    expect(screen.getByText(/View impact evidence/)).toBeInTheDocument();
  });

  it("clears stale incremental evidence when a replacement lookup fails", async () => {
    const user = userEvent.setup();
    let requestCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => {
        requestCount += 1;
        return Promise.resolve(
          requestCount === 1
            ? jsonResponse({
                run_id: "incremental-1",
                status: "completed",
                change_kind: "source_changed",
                evidence: { full_rerun: false },
                measurement: {},
                artifacts: [],
              })
            : jsonResponse(
                {
                  code: "incremental_run_not_found",
                  detail: "The incremental run was not found.",
                },
                false,
              ),
        );
      }),
    );

    render(<IncrementalPanel corpora={[]} />);
    await user.click(screen.getByText("Technical lookup"));
    await user.type(screen.getByLabelText("Corpus"), "corpus-1");
    const runInput = screen.getByLabelText("Incremental run ID");
    await user.type(runInput, "incremental-1");
    await user.click(
      screen.getByRole("button", { name: "Load update evidence" }),
    );
    expect(await screen.findByText("Source Changed")).toBeInTheDocument();

    await user.clear(runInput);
    await user.type(runInput, "incremental-2");
    await user.click(
      screen.getByRole("button", { name: "Load update evidence" }),
    );
    expect(
      await screen.findByText("The incremental run was not found."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Source Changed")).not.toBeInTheDocument();
  });
});
