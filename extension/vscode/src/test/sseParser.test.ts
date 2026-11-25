import { describe, it } from 'node:test';
import * as assert from 'node:assert';
import { SSEParser } from '../api/sseParser';

describe('EdgeMind SSEParser Wire Protocol Tests', () => {
  it('1. should parse standard event, id, and data lines with LF delimiter', () => {
    const parser = new SSEParser();
    const raw = 'id: 1\nevent: diagnosis_started\ndata: {"session_id":"s1"}\n\n';
    const events = Array.from(parser.feed(raw));

    assert.strictEqual(events.length, 1);
    assert.strictEqual(events[0].id, '1');
    assert.strictEqual(events[0].event, 'diagnosis_started');
    assert.strictEqual(events[0].data, '{"session_id":"s1"}');
  });

  it('2. should parse CRLF (\\r\\n) delimiters seamlessly', () => {
    const parser = new SSEParser();
    const raw = 'id: 42\r\nevent: response_chunk\r\ndata: {"chunk":"hello"}\r\n\r\n';
    const events = Array.from(parser.feed(raw));

    assert.strictEqual(events.length, 1);
    assert.strictEqual(events[0].id, '42');
    assert.strictEqual(events[0].event, 'response_chunk');
    assert.strictEqual(events[0].data, '{"chunk":"hello"}');
  });

  it('3. should concatenate multiple data lines with \\n', () => {
    const parser = new SSEParser();
    const raw = 'event: message\ndata: line 1\ndata: line 2\ndata: line 3\n\n';
    const events = Array.from(parser.feed(raw));

    assert.strictEqual(events.length, 1);
    assert.strictEqual(events[0].data, 'line 1\nline 2\nline 3');
  });

  it('4. should handle SSE frames split across arbitrary transport chunk boundaries', () => {
    const parser = new SSEParser();
    // Frame split across 3 chunks
    const chunk1 = 'id: 1\neve';
    const chunk2 = 'nt: custom\ndata: {"pa';
    const chunk3 = 'rt":"done"}\n\n';

    const events1 = Array.from(parser.feed(chunk1));
    assert.strictEqual(events1.length, 0);

    const events2 = Array.from(parser.feed(chunk2));
    assert.strictEqual(events2.length, 0);

    const events3 = Array.from(parser.feed(chunk3));
    assert.strictEqual(events3.length, 1);
    assert.strictEqual(events3[0].id, '1');
    assert.strictEqual(events3[0].event, 'custom');
    assert.strictEqual(events3[0].data, '{"part":"done"}');
  });

  it('5. should handle multi-byte UTF-8 sequences split across binary chunks', () => {
    const parser = new SSEParser();
    // The brain emoji '🧠' is 4 bytes in UTF-8: [0xF0, 0x9F, 0xA7, 0xA0]
    const header = Buffer.from('event: chunk\ndata: ');
    const brainPart1 = Buffer.from([0xF0, 0x9F]);
    const brainPart2 = Buffer.from([0xA7, 0xA0]);
    const trailer = Buffer.from('\n\n');

    const chunk1 = Buffer.concat([header, brainPart1]);
    const chunk2 = Buffer.concat([brainPart2, trailer]);

    const events1 = Array.from(parser.feed(chunk1));
    assert.strictEqual(events1.length, 0);

    const events2 = Array.from(parser.feed(chunk2));
    assert.strictEqual(events2.length, 1);
    assert.strictEqual(events2[0].data, '🧠');
  });

  it('6. should parse multiple complete events within a single chunk', () => {
    const parser = new SSEParser();
    const raw = (
      'event: ev1\ndata: {"n":1}\n\n' +
      'event: ev2\ndata: {"n":2}\n\n' +
      'event: ev3\ndata: {"n":3}\n\n'
    );
    const events = Array.from(parser.feed(raw));

    assert.strictEqual(events.length, 3);
    assert.strictEqual(events[0].event, 'ev1');
    assert.strictEqual(events[1].event, 'ev2');
    assert.strictEqual(events[2].event, 'ev3');
  });

  it('7. should ignore SSE comments beginning with :', () => {
    const parser = new SSEParser();
    const raw = ': heartbeat\n: another comment\nevent: ok\ndata: test\n\n: final ping\n';
    const events = Array.from(parser.feed(raw));

    assert.strictEqual(events.length, 1);
    assert.strictEqual(events[0].event, 'ok');
    assert.strictEqual(events[0].data, 'test');
  });

  it('8. should ignore consecutive empty lines without emitting blank events', () => {
    const parser = new SSEParser();
    const raw = '\n\n\n\r\n\r\nevent: valid\ndata: 123\n\n\n\n';
    const events = Array.from(parser.feed(raw));

    assert.strictEqual(events.length, 1);
    assert.strictEqual(events[0].event, 'valid');
    assert.strictEqual(events[0].data, '123');
  });

  it('9. should strip single leading space from field value', () => {
    const parser = new SSEParser();
    // 'data:  two spaces' -> value should have 1 leading space
    const raw = 'event: test\ndata:  two spaces\n\n';
    const events = Array.from(parser.feed(raw));

    assert.strictEqual(events.length, 1);
    assert.strictEqual(events[0].data, ' two spaces');
  });

  it('10. should flush trailing un-delimited event at EOF', () => {
    const parser = new SSEParser();
    // No trailing \n\n
    const raw = 'event: last\ndata: final';
    const events = Array.from(parser.feed(raw));
    assert.strictEqual(events.length, 0);

    const trailing = parser.flush();
    assert.ok(trailing);
    assert.strictEqual(trailing?.event, 'last');
    assert.strictEqual(trailing?.data, 'final');
  });

  it('11. should reset parser state cleanly', () => {
    const parser = new SSEParser();
    parser.feed('event: partial\ndata: uncompleted');
    parser.reset();

    const trailing = parser.flush();
    assert.strictEqual(trailing, null);

    const events = Array.from(parser.feed('event: fresh\ndata: 1\n\n'));
    assert.strictEqual(events.length, 1);
    assert.strictEqual(events[0].event, 'fresh');
  });

  it('12. should safely parse valid and invalid JSON data with parseJsonData', () => {
    // Valid JSON
    const valid = SSEParser.parseJsonData<{ a: number }>('{"a":10}');
    assert.deepStrictEqual(valid, { a: 10 });

    // Invalid JSON returns null without throwing
    const invalid = SSEParser.parseJsonData('{"a": broken json');
    assert.strictEqual(invalid, null);

    // Empty or non-string
    assert.strictEqual(SSEParser.parseJsonData(''), null);
  });
});
