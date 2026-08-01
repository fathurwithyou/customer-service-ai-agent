import { useConversation } from "./useConversation";

export function Header() {
  const { state } = useConversation();
  return (
    <header>
      <h1>TokoKita — customer service</h1>
      <span className="who">
        {state.customerName ? `· ${state.customerName}` : "· belum dikenali"}
      </span>
    </header>
  );
}
