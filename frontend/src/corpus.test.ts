import { describe, expect, it } from "vitest";

import {
  corpusDisplayName,
  corpusOptionLabel,
  corpusPrimaryLabel,
  shortId,
} from "./corpus";
import type { CorpusSummary, SourceSummary } from "./types";

const first: CorpusSummary = {
  id: "11111111-1111-1111-1111-111111116e8d",
  name: "Shared Delivery Corpus",
  domain: "software_delivery",
  declared_formats: ["txt"],
  created_at: "2026-08-20T04:40:00Z",
};

const second: CorpusSummary = {
  id: "22222222-2222-2222-2222-222222222647",
  name: "Shared Delivery Corpus",
  domain: "software_delivery",
  declared_formats: ["md"],
  created_at: "2026-08-21T04:40:00Z",
};

const sources: SourceSummary[] = [
  {
    id: "source-1",
    corpus_id: first.id,
    logical_name: "Project Charter",
    created_at: "2026-08-20T04:40:00Z",
  },
  {
    id: "source-2",
    corpus_id: first.id,
    logical_name: "Weekly Status",
    created_at: "2026-08-20T05:00:00Z",
  },
];

describe("corpusOptionLabel", () => {
  it("uses API corpus names and real source counts, not hardcoded project names", () => {
    const unique: CorpusSummary = {
      ...first,
      name: "Northwind Assurance",
      id: "33333333-3333-3333-3333-333333333333",
    };
    const label = corpusOptionLabel(unique, sources, false);
    expect(label).toContain("Northwind Assurance");
    expect(label).toContain("2 documents");
    expect(label).not.toContain("Aurora");
    expect(label).not.toContain("Harbor");
  });

  it("strips a trailing UUID from an API display name without hardcoding project names", () => {
    const labeled: CorpusSummary = {
      ...first,
      name: "Northwind Assurance 33333333-3333-3333-3333-333333333333",
    };
    expect(corpusDisplayName(labeled)).toBe("Northwind Assurance");
    expect(corpusPrimaryLabel(labeled, true)).toBe(
      `Northwind Assurance · …${shortId(labeled.id)}`,
    );
    expect(corpusPrimaryLabel(labeled, true)).not.toContain(
      "33333333-3333-3333-3333-333333333333",
    );
  });
  it("distinguishes duplicate display names with a shortened id", () => {
    const firstLabel = corpusPrimaryLabel(first, true);
    const secondLabel = corpusPrimaryLabel(second, true);
    expect(firstLabel).toBe(`Shared Delivery Corpus · …${shortId(first.id)}`);
    expect(secondLabel).toBe(`Shared Delivery Corpus · …${shortId(second.id)}`);
    expect(firstLabel).not.toBe(secondLabel);
    expect(firstLabel).not.toContain(first.id);
  });
});
