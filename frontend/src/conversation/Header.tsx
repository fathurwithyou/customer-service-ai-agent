import { useEffect, useState } from "react";

import { ConversationList } from "./ConversationList";
import { useConversation } from "./useConversation";

export function Header() {
  const { state } = useConversation();
  // A hairline only once it is actually overlapping content, so it does not draw a line under
  // an empty page.
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    const onScroll = () => setStuck(window.scrollY > 4);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={stuck ? "stuck" : ""}>
      <h1>TokoKita</h1>
      {state.customerName ? (
        <span className="who known">{state.customerName}</span>
      ) : (
        <span className="who">belum dikenali</span>
      )}
      <ConversationList />
    </header>
  );
}
