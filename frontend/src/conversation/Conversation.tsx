import { useCallback, useEffect, useMemo, useState } from "react";
import { ConversationContext } from "./context";
import { clearSession, recallName, rememberName, sessionId as storedSessionId } from "./session";
import { readEvents } from "./stream";
import type { Activity, ConversationState, Turn } from "./types";

const OPENING: Extract<Turn, { role: "agent" }> = {
  role: "agent",
  text: "",
  escalated: false,
  ticketId: null,
  streaming: true,
  activity: [],
};

/** The only place that knows how a conversation is driven. Components below read the
 *  contract; swapping SSE for websockets or a fake would not reach them. */
export function Conversation({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState(storedSessionId);
  const [state, setState] = useState<ConversationState>({
    turns: [],
    customerName: recallName(),
    busy: false,
    loading: true,
  });

  // A refresh continues the conversation: the server already holds every message, so the client
  // asks for it rather than keeping a second copy that could disagree.
  useEffect(() => {
    let live = true;
    fetch(`/chat/${encodeURIComponent(sessionId)}`)
      .then((r) => (r.ok ? r.json() : []))
      .then((rows: { role: string; text: string; activity: Activity[] }[]) => {
        if (!live) return;
        setState((s) => ({
          ...s,
          loading: false,
          turns: rows.map((r) =>
            r.role === "customer"
              ? { role: "customer", text: r.text }
              : { ...OPENING, text: r.text, streaming: false, activity: r.activity },
          ),
        }));
      })
      .catch(() => live && setState((s) => ({ ...s, loading: false })));
    return () => {
      live = false;
    };
  }, [sessionId]);

  const send = useCallback(
    async (message: string, customerHint: string | null) => {
      setState((s) => ({
        ...s,
        busy: true,
        turns: [...s.turns, { role: "customer", text: message }, { ...OPENING }],
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
        const activity: Activity[] = [];
        for await (const [name, data] of readEvents(res.body)) {
          if (name === "start") {
            rememberName(data.customer_name ?? null);
            setState((s) => ({ ...s, customerName: data.customer_name ?? null }));
          } else if (name === "tool") {
            // A retried call repeats its phrase; the customer is being shown a phase, not a
            // call log, so a repeat would read as the agent doing the same thing twice.
            if (activity.at(-1)?.label !== data.label) activity.push(data as Activity);
            patchAgent({ activity: [...activity] });
          } else if (name === "delta") {
            text += data.text;
            patchAgent({ text });
          } else if (name === "done") {
            patchAgent({
              text: data.message || text,
              escalated: Boolean(data.escalated),
              ticketId: data.ticket_id ?? null,
              streaming: false,
            });
          }
        }
      } catch {
        patchAgent({ text: "Maaf, koneksi terputus. Coba kirim ulang pesannya.", streaming: false });
      } finally {
        setState((s) => ({ ...s, busy: false }));
      }
    },
    [sessionId],
  );

  const reset = useCallback(() => {
    clearSession();
    setState({ turns: [], customerName: null, busy: false, loading: false });
    setSessionId(storedSessionId());
  }, []);

  const value = useMemo(
    () => ({ state, actions: { send, reset }, meta: { sessionId } }),
    [state, send, reset, sessionId],
  );
  return <ConversationContext value={value}>{children}</ConversationContext>;
}
