/**
 * Query keys shared by screens and by the live-event invalidation map, so a server event refetches exactly the
 * queries that show that data. Later slices build their queries on these keys.
 */
export const queryKeys = {
  conversations: ["conversations"] as const,
  conversation: (id: string) => ["conversations", id] as const,
  escalations: ["escalations"] as const,
  documents: ["documents"] as const,
  ingestionJob: (id: string) => ["ingestion-jobs", id] as const,
  teamMembers: ["team", "members"] as const,
};
