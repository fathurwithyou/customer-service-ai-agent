export type Turn =
  | { role: "customer"; text: string }
  | {
      role: "agent";
      text: string;
      escalated: boolean;
      ticketId: number | null;
      streaming: boolean;
      /** What the agent is doing right now, in the customer's language. Cleared once text starts. */
      activity: string | null;
    };

export interface ConversationState {
  turns: Turn[];
  customerName: string | null;
  /** A turn is in flight; the composer stays disabled until it settles. */
  busy: boolean;
}

export interface ConversationActions {
  send: (message: string, customerHint: string | null) => Promise<void>;
}

export interface ConversationMeta {
  sessionId: string;
}

export interface ConversationContextValue {
  state: ConversationState;
  actions: ConversationActions;
  meta: ConversationMeta;
}
