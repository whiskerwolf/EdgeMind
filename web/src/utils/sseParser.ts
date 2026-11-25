export interface RawSSEEvent {
  id?: string;
  event: string;
  data: string;
}

/**
 * Browser-safe RFC 8895 Server-Sent Events incremental parser.
 * Handles split transport chunks, multi-byte UTF-8 sequences, LF/CRLF newlines,
 * multi-line data payloads, and comment/heartbeat frames.
 */
export class SSEParser {
  private buffer = '';
  private currentId?: string;
  private currentEvent = 'message';
  private currentDataLines: string[] = [];
  private decoder = new TextDecoder('utf-8', { fatal: false, ignoreBOM: true });

  public *feed(chunk: Uint8Array | string): Generator<RawSSEEvent> {
    const text =
      typeof chunk === 'string' ? chunk : this.decoder.decode(chunk, { stream: true });

    this.buffer += text;

    let lineStart = 0;
    while (true) {
      const lfIdx = this.buffer.indexOf('\n', lineStart);
      if (lfIdx === -1) {
        this.buffer = this.buffer.slice(lineStart);
        break;
      }

      let line = this.buffer.slice(lineStart, lfIdx);
      if (line.endsWith('\r')) {
        line = line.slice(0, -1);
      }
      lineStart = lfIdx + 1;

      if (line === '') {
        if (
          this.currentDataLines.length > 0 ||
          this.currentEvent !== 'message' ||
          this.currentId !== undefined
        ) {
          const event: RawSSEEvent = {
            id: this.currentId,
            event: this.currentEvent,
            data: this.currentDataLines.join('\n'),
          };
          this.currentEvent = 'message';
          this.currentDataLines = [];
          yield event;
        }
        continue;
      }

      if (line.startsWith(':')) {
        continue;
      }

      this.consumeFieldLine(line);
    }
  }

  public flush(): RawSSEEvent | null {
    const remainingText = this.decoder.decode();
    if (remainingText) {
      this.buffer += remainingText;
    }

    if (this.buffer.length > 0) {
      let line = this.buffer;
      if (line.endsWith('\r')) {
        line = line.slice(0, -1);
      }
      if (!line.startsWith(':')) {
        this.consumeFieldLine(line);
      }
      this.buffer = '';
    }

    if (
      this.currentDataLines.length > 0 ||
      (this.currentEvent !== 'message' && this.currentEvent !== '')
    ) {
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

  private consumeFieldLine(line: string): void {
    const colonIdx = line.indexOf(':');
    const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
    let value = colonIdx === -1 ? '' : line.slice(colonIdx + 1);
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
