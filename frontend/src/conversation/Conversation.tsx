import { useCallback, useMemo, useRef, useState } from "react";
import { ConversationContext } from "./context";
import { readEvents } from "./stream";
import type { ConversationState, Turn } from "./types";

/** The only place that knows how a conversation is driven. Components below read the
 *  contract; swapping SSE for websockets or a fake would not reach them. */
export function Conversation({ children }: { children: React.ReactNode }) {
  const sessionId = useRef("web-" + Math.random().toString(36).slice(2, 8)).current;
  const [state, setState] = useState<ConversationState>({
    turns: [],
    customerName: null,
    busy: false,
  });

  const send = useCallback(
    async (message: string, customerHint: string | null) => {
      const agent: Turn = {
        role: "agent",
        text: "",
        escalated: false,
        ticketId: null,
        streaming: true,
        activity: null,
      };
      setState((s) => ({
        ...s,
        busy: true,
        turns: [...s.turns, { role: "customer", text: message }, agent],
      }));

      const patchAgent = (patch: Partial<Extract<Turn, { role: "agent" }>>) =>
        setState((s) => {
          const turns = s.turns.slice();
          const last = turns.at(-1);
          if (last?.role === "agent") turns[turns.length - 1] = { ...last, ...patch };
          return { ...s, turns };
        });

      try {
        const res = await fetch("/chat/stream", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, customer_hint: customerHint, message }),
        });
        if (!res.body) throw new Error("no stream");

        let text = "";
        for await (const [name, data] of readEvents(res.body)) {
          if (name === "start") {
            setState((s) => ({ ...s, customerName: data.customer_name ?? null }));
          } else if (name === "tool") {
            patchAgent({ activity: data.label });
          } else if (name === "delta") {
            text += data.text;
            patchAgent({ text, activity: null });
          } else if (name === "done") {
            patchAgent({
              text: data.message || text,
              escalated: Boolean(data.escalated),
              ticketId: data.ticket_id ?? null,
              streaming: false,
              activity: null,
            });
          }
        }
      } catch {
        patchAgent({
          text: "Maaf, koneksi terputus. Coba kirim ulang pesannya.",
          streaming: false,
          activity: null,
        });
      } finally {
        setState((s) => ({ ...s, busy: false }));
      }
    },
    [sessionId],
  );

  const value = useMemo(
    () => ({ state, actions: { send }, meta: { sessionId } }),
    [state, send, sessionId],
  );
  return <ConversationContext value={value}>{children}</ConversationContext>;
}
