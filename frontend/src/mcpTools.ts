/**
 * Compile-time MCP business-tool registry synchronized with
 * backend/src/app/mcp_server.py `BUSINESS_TOOL_NAMES`.
 *
 * No HTTP endpoint exposes the MCP tool list to the frontend. Counts and names
 * rendered in the UI are derived from this registry, not invented literals.
 */
export const MCP_TOOL_GROUPS = [
  {
    label: "Corpus",
    tools: ["list_corpora", "get_corpus", "list_sources"],
  },
  {
    label: "Agent workflow",
    tools: [
      "start_workflow",
      "get_workflow_status",
      "resume_workflow",
      "get_understanding",
      "get_examination",
    ],
  },
  {
    label: "Human review",
    tools: [
      "open_review",
      "list_review_items",
      "approve_review_item",
      "reject_review_item",
      "edit_review_item",
      "complete_review",
    ],
  },
  {
    label: "Publication",
    tools: ["publish_register", "get_current_register", "get_register"],
  },
  {
    label: "Incremental",
    tools: [
      "get_current_revision",
      "start_incremental_run",
      "get_incremental_evidence",
    ],
  },
] as const;

export const MCP_TOOL_COUNT = MCP_TOOL_GROUPS.reduce(
  (total, group) => total + group.tools.length,
  0,
);
