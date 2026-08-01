/** Parse an SSE body into (event, data) pairs. Kept apart from React so the transport can be
 *  replaced -- or tested -- without a component in the way. */
export async function* readEvents(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const name = frame.match(/^event: (.+)$/m)?.[1];
      const payload = frame.match(/^data: (.+)$/m)?.[1];
      if (name && payload) yield [name, JSON.parse(payload)] as const;
    }
  }
}
