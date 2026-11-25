/**
 * Robust, spec-compliant Server-Sent Events (SSE) Wire Parser (RFC 8895).
 *
 * Capabilities:
 * - Handles arbitrary transport chunk boundaries (split event headers and JSON payloads)
 * - Reassembles multi-byte UTF-8 sequences split across byte chunks using TextDecoder streaming
 * - Supports both CRLF (\r\n) and LF (\n) line delimiters
 * - Supports multiple events within a single transport chunk
 * - Concatenates multiple data: lines with \n
 * - Strips single leading space from field values per SSE spec
 * - Ignores SSE comments (: comment / : heartbeat)
 * - Ignores consecutive empty lines
 * - Safely parses JSON payloads without throwing unhandled exceptions
 */

export interface RawSSEEvent {
  id?: string;
  event: string;
  data: string;
}

export class SSEParser {
  private buffer = '';
  private currentId?: string;
  private currentEvent = 'message';
  private currentDataLines: string[] = [];
  private decoder = new TextDecoder('utf-8', { fatal: false, ignoreBOM: true });

  /**
   * Feed incremental Uint8Array binary chunk or string into the parser.
   * Yields complete parsed RawSSEEvent instances.
   */
  public *feed(chunk: Uint8Array | string): Generator<RawSSEEvent> {
    const text = typeof chunk === 'string'
      ? chunk
      : this.decoder.decode(chunk, { stream: true });

    this.buffer += text;

    let lineStart = 0;
    while (true) {
      const lfIdx = this.buffer.indexOf('\n', lineStart);
      if (lfIdx === -1) {
        // Retain unparsed line fragment in buffer for next chunk
        this.buffer = this.buffer.slice(lineStart);
        break;
      }

      let line = this.buffer.slice(lineStart, lfIdx);
      if (line.endsWith('\r')) {
        line = line.slice(0, -1);
      }
      lineStart = lfIdx + 1;

      // Empty line signals event dispatch boundary
      if (line === '') {
        if (this.currentDataLines.length > 0 || this.currentEvent !== 'message' || this.currentId !== undefined) {
          const event: RawSSEEvent = {
            id: this.currentId,
            event: this.currentEvent,
            data: this.currentDataLines.join('\n'),
          };
          // Reset per-event fields for the next event
          this.currentEvent = 'message';
          this.currentDataLines = [];
          yield event;
        }
        continue;
      }

      // Ignore comment lines beginning with ':'
      if (line.startsWith(':')) {
        continue;
      }

      // Parse field name and value
      const colonIdx = line.indexOf(':');
      let field: string;
      let value: string;

      if (colonIdx === -1) {
        field = line;
        value = '';
      } else {
        field = line.slice(0, colonIdx);
        value = line.slice(colonIdx + 1);
        if (value.startsWith(' ')) {
          value = value.slice(1);
        }
      }

      if (field === 'event') {
        this.currentEvent = value;
      } else if (field === 'data') {
        this.currentDataLines.push(value);
      } else if (field === 'id') {
        this.currentId = value;
      }
    }
  }

  /**
   * Flush any remaining bytes from decoder and emit any un-dispatched event at EOF.
   */
  public flush(): RawSSEEvent | null {
    const remainingText = this.decoder.decode();
    if (remainingText) {
      this.buffer += remainingText;
    }

    if (this.buffer.length > 0) {
      // Process any uncompleted trailing line in the buffer
      let line = this.buffer;
      if (line.endsWith('\r')) {
        line = line.slice(0, -1);
      }
      if (!line.startsWith(':')) {
        const colonIdx = line.indexOf(':');
        if (colonIdx !== -1) {
          const field = line.slice(0, colonIdx);
          let value = line.slice(colonIdx + 1);
          if (value.startsWith(' ')) {
            value = value.slice(1);
          }
          if (field === 'event') {
            this.currentEvent = value;
          } else if (field === 'data') {
            this.currentDataLines.push(value);
          } else if (field === 'id') {
            this.currentId = value;
          }
        }
      }
      this.buffer = '';
    }

    if (this.currentDataLines.length > 0 || (this.currentEvent !== 'message' && this.currentEvent !== '')) {
      const event: RawSSEEvent = {
        id: this.currentId,
        event: this.currentEvent,
        data: this.currentDataLines.join('\n'),
      };
      this.currentEvent = 'message';
      this.currentDataLines = [];
      return event;
    }

    return null;
  }

  /**
   * Reset parser internal buffers and state.
   */
  public reset(): void {
    this.buffer = '';
    this.currentId = undefined;
    this.currentEvent = 'message';
    this.currentDataLines = [];
    this.decoder = new TextDecoder('utf-8', { fatal: false, ignoreBOM: true });
  }

  /**
   * Safe JSON parser utility that parses event data without throwing.
   */
  public static parseJsonData<T = unknown>(data: string): T | null {
    if (!data || typeof data !== 'string') {
      return null;
    }
    try {
      return JSON.parse(data) as T;
    } catch {
      return null;
    }
  }
}
