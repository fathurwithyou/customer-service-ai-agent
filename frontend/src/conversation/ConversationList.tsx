import { useEffect, useRef, useState } from "react";
import { Icon } from "../Icon";
import type { Summary } from "./types";
import { useConversation } from "./useConversation";

function ago(iso: string | null): string {
  if (!iso) return "";
  const mins = Math.round((Date.now() - Date.parse(iso)) / 60000);
  if (mins < 1) return "baru saja";
  if (mins < 60) return `${mins} menit lalu`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} jam lalu`;
  return `${Math.round(hours / 24)} hari lalu`;
}

function Row({
  item,
  current,
  onOpen,
}: {
  item: Summary;
  current: boolean;
  onOpen: () => void;
}) {
  const { actions } = useConversation();
  return (
    <li className={`crow ${current ? "on" : ""}`}>
      <button
        className="copen"
        type="button"
        onClick={() => {
          actions.open(item.session_id);
          onOpen();
        }}
      >
        <span className="ctext">{item.opening ?? "(kosong)"}</span>
        <span className="cmeta">
          {ago(item.last_at)} · {item.messages} pesan
        </span>
      </button>
      <button
        className="cdrop"
        type="button"
        aria-label="Hapus percakapan"
        title="Hapus percakapan"
        onClick={() => actions.forget(item.session_id)}
      >
        <Icon name="trash" />
      </button>
    </li>
  );
}

export function ConversationList() {
  const { state, actions, meta } = useConversation();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // A panel that covers the conversation has to be dismissable without choosing something.
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className={`picker ${open ? "open" : ""}`} ref={box}>
      <button className="reset" type="button" onClick={() => setOpen((o) => !o)}>
        <Icon name="list" />
        Percakapan
        {state.saved.length > 0 && <span className="count">{state.saved.length}</span>}
      </button>
      {open && (
        <div className="panel">
          <button
            className="cnew"
            type="button"
            onClick={() => {
              actions.reset();
              setOpen(false);
            }}
          >
            <Icon name="plus" />
            Percakapan baru
          </button>
          {state.saved.length === 0 ? (
            <p className="cempty">Belum ada percakapan tersimpan.</p>
          ) : (
            <ul className="clist">
              {state.saved.map((item) => (
                <Row
                  key={item.session_id}
                  item={item}
                  current={item.session_id === meta.sessionId}
                  onOpen={() => setOpen(false)}
                />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
