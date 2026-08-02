/** Declared beside the tools it names, on the server. The UI resolves `icon` to a glyph and
 *  never sees a tool name. */
export interface Activity {
  label: string;
  icon: string;
}

export type Turn =
  | { role: "customer"; text: string }
  | {
      role: "agent";
      text: string;
      escalated: boolean;
      ticketId: number | null;
      streaming: boolean;
      /** What the agent did, in the customer's language, in the order it happened. The same
       *  phrases the stream sends and the transcript endpoint replays. */
      activity: Activity[];
    };

export interface ConversationState {
  turns: Turn[];
  customerName: string | null;
  /** A turn is in flight; the composer stays disabled until it settles. */
  busy: boolean;
  /** History is still being fetched, so an empty log is not yet meaningful. */
  loading: boolean;
}

export interface ConversationActions {
  send: (message: string, customerHint: string | null) => Promise<void>;
  reset: () => void;
}

export interface ConversationMeta {
  sessionId: string;
}

export interface ConversationContextValue {
  state: ConversationState;
  actions: ConversationActions;
  meta: ConversationMeta;
}
