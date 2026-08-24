import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CorpusSelect from "./CorpusSelect";
import type { CorpusSummary, SourceSummary } from "./types";

const corpora: CorpusSummary[] = [
  {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa6e8d",
    name: "Shared Delivery Corpus",
    domain: "software_delivery",
    declared_formats: ["txt"],
    created_at: "2026-08-20T04:40:00Z",
  },
  {
    id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb2647",
    name: "Shared Delivery Corpus",
    domain: "software_delivery",
    declared_formats: ["md"],
    created_at: "2026-08-21T04:40:00Z",
  },
  {
    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
    name: "Northwind Assurance",
    domain: "software_delivery",
    declared_formats: ["txt"],
    created_at: "2026-08-22T04:40:00Z",
  },
];

const sourcesByCorpus: Record<string, SourceSummary[]> = {
  "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa6e8d": [
    {
      id: "source-1",
      corpus_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa6e8d",
      logical_name: "Charter",
      created_at: "2026-08-20T04:40:00Z",
    },
    {
      id: "source-2",
      corpus_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa6e8d",
      logical_name: "Status",
      created_at: "2026-08-20T05:00:00Z",
    },
  ],
  "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb2647": [],
  "cccccccc-cccc-cccc-cccc-cccccccccccc": [],
};

describe("CorpusSelect", () => {
  it("renders API names with short duplicate disambiguators and no full UUID in the option label", async () => {
    const user = userEvent.setup();
    render(
      <label>
        Corpus
        <CorpusSelect
          id="corpus"
          corpora={corpora}
          sourcesByCorpus={sourcesByCorpus}
          value=""
          onChange={() => undefined}
        />
      </label>,
    );

    await user.click(screen.getByLabelText("Corpus"));
    expect(
      screen.getByRole("option", {
        name: /Shared Delivery Corpus · …aaaaaaaa6e8d/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", {
        name: /Shared Delivery Corpus · …bbbbbbbb2647/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaa6e8d"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Aurora")).not.toBeInTheDocument();
    expect(screen.queryByText("Harbor")).not.toBeInTheDocument();
  });

  it("selects an option and closes the list on Escape", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <label>
        Corpus
        <CorpusSelect
          id="corpus-select"
          corpora={corpora}
          sourcesByCorpus={sourcesByCorpus}
          value="cccccccc-cccc-cccc-cccc-cccccccccccc"
          onChange={onChange}
        />
      </label>,
    );

    const trigger = screen.getByLabelText("Corpus");
    expect(trigger).toHaveAttribute(
      "data-corpus-id",
      "cccccccc-cccc-cccc-cccc-cccccccccccc",
    );
    await user.click(trigger);
    expect(
      screen.getByRole("option", { name: /Northwind Assurance/ }),
    ).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Escape}");
    expect(
      screen.queryByRole("option", { name: /Northwind Assurance/ }),
    ).not.toBeInTheDocument();
  });

  it("moves the highlight with the keyboard and never uses a full UUID as the option label", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <label>
        Corpus
        <CorpusSelect
          id="corpus-keys"
          corpora={corpora}
          sourcesByCorpus={sourcesByCorpus}
          value=""
          onChange={onChange}
        />
      </label>,
    );

    await user.click(screen.getByLabelText("Corpus"));
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith(
      "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb2647",
    );
    expect(
      screen.queryByText("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb2647"),
    ).not.toBeInTheDocument();
  });
});
