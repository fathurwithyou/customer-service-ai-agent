import { useState } from "react";
import { useConversation } from "./useConversation";

export function Composer() {
  const { state, actions } = useConversation();
  const [message, setMessage] = useState("");
  const [hint, setHint] = useState("andi@example.com");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const text = message.trim();
        if (!text || state.busy) return;
        setMessage("");
        void actions.send(text, hint.trim() || null);
      }}
    >
      <input
        className="hint"
        value={hint}
        onChange={(e) => setHint(e.target.value)}
        placeholder="email / telepon"
        aria-label="Identitas pelanggan"
      />
      <input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Tulis pesan..."
        aria-label="Pesan"
        autoFocus
      />
      <button disabled={state.busy}>Kirim</button>
    </form>
  );
}
