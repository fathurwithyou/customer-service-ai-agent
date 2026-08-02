import { useState } from "react";
import { Icon } from "../Icon";
import type { Activity } from "./types";

/** What the agent did before answering, as a collapsible timeline.
 *
 *  Each row is a capability's own phrase and glyph -- "Melacak posisi paket" -- never a tool
 *  name. The customer is shown that their data was looked up, not that a function was called. */

/** The shell. It takes a glyph, a title and children, and decides nothing: no `done` flag to
 *  read, so it cannot grow a second meaning. */
function Group({
  glyph,
  title,
  children,
}: {
  glyph: React.ReactNode;
  title: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className={`work ${open ? "open" : ""}`}>
      <button className="whead" onClick={() => setOpen((o) => !o)} type="button">
        {glyph}
        {title}
        <span className="chev" />
      </button>
      <div className="wbody">
        <div>
          <ol className="witems">{children}</ol>
        </div>
      </div>
    </div>
  );
}

function Step({ step }: { step: Activity }) {
  return (
    <li className="titem">
      <span className="tcol">
        <span className="tico">
          <Icon name={step.icon} />
        </span>
        <span className="tline" />
      </span>
      <span className="tbody">{step.label}</span>
    </li>
  );
}

function RunningStep({ step }: { step: Activity }) {
  return (
    <li className="titem busy">
      <span className="tcol">
        <span className="tico">
          <Icon name={step.icon} />
        </span>
        <span className="tline" />
      </span>
      <span className="tbody">{step.label}</span>
    </li>
  );
}

export function WorkInProgress({ items }: { items: Activity[] }) {
  if (!items.length) return null;
  // Only the newest step is still running; the ones above it have already returned.
  const last = items.length - 1;
  return (
    <Group
      glyph={<span className="wglyph spin" />}
      title={<span className="wtitle pulse">Sedang mencari data Anda</span>}
    >
      {items.map((step, i) =>
        i === last ? <RunningStep key={i} step={step} /> : <Step key={i} step={step} />,
      )}
    </Group>
  );
}

export function WorkDone({ items }: { items: Activity[] }) {
  if (!items.length) return null;
  return (
    <Group
      glyph={
        <span className="wglyph done">
          <Icon name="check" />
        </span>
      }
      title={<span className="wtitle">{`Selesai · ${items.length} langkah`}</span>}
    >
      {items.map((step, i) => (
        <Step key={i} step={step} />
      ))}
    </Group>
  );
}
