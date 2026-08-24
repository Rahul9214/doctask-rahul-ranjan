export interface Workspace {
  corpusId: string;
  workflowRunId: string;
  examinationRunId: string;
  reviewSessionId: string;
  workflowStatus: string | null;
  reviewStatus: string | null;
}

export const emptyWorkspace: Workspace = {
  corpusId: "",
  workflowRunId: "",
  examinationRunId: "",
  reviewSessionId: "",
  workflowStatus: null,
  reviewStatus: null,
};

export function workspaceFromRun(run: {
  id: string;
  corpus_id: string;
  status: string;
  examination_run_id: string | null;
  review_session_id: string | null;
}): Workspace {
  return {
    corpusId: run.corpus_id,
    workflowRunId: run.id,
    examinationRunId: run.examination_run_id ?? "",
    reviewSessionId: run.review_session_id ?? "",
    workflowStatus: run.status,
    reviewStatus: null,
  };
}
