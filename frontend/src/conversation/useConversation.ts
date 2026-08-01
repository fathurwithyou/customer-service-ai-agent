import { use } from "react";
import { ConversationContext } from "./context";

export function useConversation() {
  const value = use(ConversationContext);
  if (!value) throw new Error("useConversation must be used inside <Conversation>");
  return value;
}
