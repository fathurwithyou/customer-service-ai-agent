import { useEffect, useRef } from "react";

import { Markdown } from "../Markdown";
import type { Turn } from "./types";
import { useConversation } from "./useConversation";
import { WorkDone, WorkInProgress } from "./WorkGroup";

type AgentTurn = Extract<Turn, { role: "agent" }>;

/** Explicit variants rather than <Turn isAgent isStreaming>: an agent turn passes through three
 *  states that share almost no markup, and a boolean prop would hide that behind a flag. */

function CustomerTurn({ text }: { text: string }) {
  return <div className="customer">{text}</div>;
}

function Dots() {
  return (
    <span className="dots">
      {[0, 1, 2].map((i) => (
        <i key={i} style={{ "--i": i } as React.CSSProperties} />
      ))}
    </span>
  );
}

function Badges({ escalated, ticketId }: { escalated: boolean; ticketId: number | null }) {
  if (!escalated && !ticketId) return null;
  return (
    <div className="badges">
      {escalated && <span className="badge esc">diteruskan ke tim manusia</span>}
      {ticketId && <span className="badge">tiket #{ticketId}</span>}
    </div>
  );
}

/** Nothing to read yet: the customer sees the work instead of an empty box. */
function ThinkingTurn({ turn }: { turn: AgentTurn }) {
  return (
    <div className="agent">
      <WorkInProgress items={turn.activity} />
      {!turn.activity.length && <Dots />}
    </div>
  );
}

/** The answer is arriving. The work group stays above it, collapsed by the customer if they
 *  would rather just read. */
function WritingTurn({ turn }: { turn: AgentTurn }) {
  return (
    <div className="agent">
      <WorkInProgress items={turn.activity} />
      <Markdown text={turn.text} />
      <span className="caret" />
    </div>
  );
}

/** Settled -- and identical whether it just finished or was replayed from the transcript on a
 *  refresh, which is what makes a reloaded conversation indistinguishable from a live one. */
function AnsweredTurn({ turn }: { turn: AgentTurn }) {
  return (
    <div className="agent">
      <WorkDone items={turn.activity} />
      <Markdown text={turn.text} />
      <Badges escalated={turn.escalated} ticketId={turn.ticketId} />
    </div>
  );
}

/** Follows the answer as it streams -- but stops the moment the customer scrolls up to re-read.
 *
 *  Listening to `scroll` would be wrong: a smooth `scrollIntoView` fires it too, and the
 *  midpoint of that animation is never "near the bottom", so following would switch itself off
 *  on the first frame. Wheel, touch and the paging keys are the events only a person produces. */
function useFollow(dep: unknown) {
  const end = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  useEffect(() => {
    const atBottom = () =>
      window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 140;
    const reconsider = () => {
      pinned.current = atBottom();
    };
    const keys = new Set(["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"]);
    const onKey = (e: KeyboardEvent) => keys.has(e.key) && reconsider();
    window.addEventListener("wheel", reconsider, { passive: true });
    window.addEventListener("touchmove", reconsider, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("wheel", reconsider);
      window.removeEventListener("touchmove", reconsider);
      window.removeEventListener("keydown", onKey);
    };
  }, []);
  const settled = useRef(false);
  useEffect(() => {
    if (!pinned.current) return;
    // A frame later: the effect runs before the browser has laid the new markdown out, so
    // scrolling now would aim at a position that is about to move.
    const id = requestAnimationFrame(() => {
      end.current?.scrollIntoView({
        block: "end",
        // The first jump is the replayed transcript arriving at once. Animating it would scroll
        // the whole history past the reader for no reason.
        behavior: settled.current ? "smooth" : "auto",
      });
      settled.current = true;
    });
    return () => cancelAnimationFrame(id);
  }, [dep]);
  return end;
}

export function Log() {
  const { state } = useConversation();
  const end = useFollow(state.turns);
  if (state.loading) return <div className="log" />;
  return (
    <div className="log">
      {state.turns.map((turn, i) => {
        if (turn.role === "customer") return <CustomerTurn key={i} text={turn.text} />;
        if (!turn.streaming) return <AnsweredTurn key={i} turn={turn} />;
        return turn.text ? (
          <WritingTurn key={i} turn={turn} />
        ) : (
          <ThinkingTurn key={i} turn={turn} />
        );
      })}
      <div ref={end} className="end" />
    </div>
  );
}
