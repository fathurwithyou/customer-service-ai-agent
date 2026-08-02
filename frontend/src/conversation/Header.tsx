import { useConversation } from "./useConversation";

export function Header() {
  const { state, actions } = useConversation();
  return (
    <header>
      <h1>TokoKita</h1>
      {state.customerName ? (
        <span className="who known">{state.customerName}</span>
      ) : (
        <span className="who">belum dikenali</span>
      )}
      {state.turns.length > 0 && (
        <button className="reset" onClick={actions.reset} type="button">
          Percakapan baru
        </button>
      )}
    </header>
  );
}
