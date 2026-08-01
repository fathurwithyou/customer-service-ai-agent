import { Composer, Conversation, Header, Log } from "./conversation";

/** Compound shape: the provider owns the turn state, the pieces below just read it, so the
 *  page can be rearranged without threading props through. */
export function App() {
  return (
    <Conversation>
      <Header />
      <Log />
      <Composer />
    </Conversation>
  );
}
