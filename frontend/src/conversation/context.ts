import { createContext } from "react";
import type { ConversationContextValue } from "./types";

/** The contract the UI consumes. Any provider that satisfies it can drive the same views --
 *  which is what lets a test or a demo swap the transport without touching a component. */
export const ConversationContext = createContext<ConversationContextValue | null>(null);
