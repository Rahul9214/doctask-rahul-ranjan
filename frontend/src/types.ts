export interface CorpusSummary {
  id: string;
  name: string;
  domain: string;
  declared_formats: string[];
  created_at: string;
}

export interface SourceSummary {
  id: string;
  corpus_id: string;
  logical_name: string;
  created_at: string;
}
