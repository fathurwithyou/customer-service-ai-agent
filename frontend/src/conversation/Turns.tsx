import { Markdown } from "../Markdown";
import type { Turn } from "./types";
import { useConversation } from "./useConversation";

/** Explicit variants rather than <Turn isAgent>: the two roles share no markup worth uniting,
 *  and a boolean would hide that. */
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

/** Says what is happening while there is nothing to read yet. Phrased for a customer -- the
 *  point is that they can see their data being looked up, not that a tool ran. */
function Working({ label }: { label: string | null }) {
  return (
    <span className="working">
      <Dots />
      {label && <span className="wlabel">{label}</span>}
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

function AgentTurn({ turn }: { turn: Extract<Turn, { role: "agent" }> }) {
  if (turn.streaming && !turn.text)
    return (
      <div className="agent">
        <Working label={turn.activity} />
      </div>
    );
  return (
    <div className="agent">
      <Markdown text={turn.text} />
      {turn.streaming ? <span className="caret" /> : <Badges {...turn} ticketId={turn.ticketId} />}
    </div>
  );
}

export function Log() {
  const { state } = useConversation();
  return (
    <div className="log">
      {state.turns.map((turn, i) =>
        turn.role === "customer" ? (
          <CustomerTurn key={i} text={turn.text} />
        ) : (
          <AgentTurn key={i} turn={turn} />
        ),
      )}
    </div>
  );
}
