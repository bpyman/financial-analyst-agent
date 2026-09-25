export interface SseMessage {
  event: string;
  data: string;
}

/**
 * Incremental text/event-stream parser. Feed decoded chunks; get back every
 * complete message. Handles CRLF, multi-line data, and chunk boundaries that
 * split a message anywhere.
 */
export function createSseParser(): (chunk: string) => SseMessage[] {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk.replace(/\r\n?/g, "\n");
    const messages: SseMessage[] = [];
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (!line || line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        let value = colon === -1 ? "" : line.slice(colon + 1);
        if (value.startsWith(" ")) value = value.slice(1);
        if (field === "event") event = value;
        else if (field === "data") data.push(value);
      }
      if (data.length) messages.push({ event, data: data.join("\n") });
      boundary = buffer.indexOf("\n\n");
    }
    return messages;
  };
}
