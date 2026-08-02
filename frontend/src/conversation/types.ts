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

/** A row in the picker. `opening` is the customer's first message, read out of the stored
 *  payload rather than kept in a second column. */
export interface Summary {
  session_id: string;
  opened_at: string | null;
  last_at: string | null;
  messages: number;
  opening: string | null;
}

export interface ConversationState {
  turns: Turn[];
  customerName: string | null;
  /** A turn is in flight; the composer stays disabled until it settles. */
  busy: boolean;
  /** History is still being fetched, so an empty log is not yet meaningful. */
  loading: boolean;
  /** Every conversation the server still holds, newest first. */
  saved: Summary[];
}

export interface ConversationActions {
  send: (message: string, customerHint: string | null) => Promise<void>;
  /** Leave this conversation for a new one. The old one is kept; use `forget` to delete it. */
  reset: () => void;
  open: (sessionId: string) => void;
  forget: (sessionId: string) => Promise<void>;
}

export interface ConversationMeta {
  sessionId: string;
}

export interface ConversationContextValue {
  state: ConversationState;
  actions: ConversationActions;
  meta: ConversationMeta;
}
