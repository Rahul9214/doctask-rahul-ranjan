import { formatCompactTimestamp } from "./ui";
import type { CorpusSummary, SourceSummary } from "./types";

export type { CorpusSummary, SourceSummary };

const TRAILING_UUID =
  /(?:\s+|·\s*)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function shortId(id: string): string {
  const compact = id.replaceAll("-", "");
  return compact.slice(-12);
}

export function corpusDisplayName(corpus: CorpusSummary): string {
  const cleaned = corpus.name.replace(TRAILING_UUID, "").trim();
  return cleaned || corpus.name;
}

export function nameCounts(corpora: CorpusSummary[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const corpus of corpora) {
    const key = corpusDisplayName(corpus);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

export function latestKnownTimestamp(
  corpus: CorpusSummary,
  sources: SourceSummary[] | undefined,
): string | undefined {
  const stamps = [
    corpus.created_at,
    ...(sources ?? []).map((source) => source.created_at),
  ].filter((value) => Boolean(value));
  if (stamps.length === 0) {
    return undefined;
  }
  return stamps.reduce((latest, current) =>
    new Date(current).getTime() > new Date(latest).getTime() ? current : latest,
  );
}

export function corpusPrimaryLabel(
  corpus: CorpusSummary,
  duplicate: boolean,
): string {
  const name = corpusDisplayName(corpus);
  return duplicate ? `${name} · …${shortId(corpus.id)}` : name;
}

export function corpusMetaLabel(
  corpus: CorpusSummary,
  sources: SourceSummary[] | undefined,
): string {
  const parts: string[] = [];
  if (sources) {
    parts.push(
      `${sources.length} ${sources.length === 1 ? "document" : "documents"}`,
    );
  }
  const timestamp = latestKnownTimestamp(corpus, sources);
  if (timestamp) {
    parts.push(formatCompactTimestamp(timestamp));
  }
  return parts.join(" · ");
}

export function corpusOptionLabel(
  corpus: CorpusSummary,
  sources: SourceSummary[] | undefined,
  duplicate: boolean,
): string {
  const primary = corpusPrimaryLabel(corpus, duplicate);
  if (duplicate) {
    return primary;
  }
  const meta = corpusMetaLabel(corpus, sources);
  return meta ? `${primary} · ${meta}` : primary;
}

export function asSourceList(body: unknown): SourceSummary[] {
  if (!Array.isArray(body)) {
    return [];
  }
  return body.filter((item): item is SourceSummary => {
    if (!item || typeof item !== "object") {
      return false;
    }
    const record = item as Partial<SourceSummary>;
    return typeof record.id === "string";
  });
}
