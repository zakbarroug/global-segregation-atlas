import { describe, expect, it } from 'vitest';
import { consumeAnalysis } from '../src/lib/stream';
import type { AnalysisEvent } from '../src/lib/types';

function response(chunks: string[]) {
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
        controller.close();
      },
    }),
    { headers: { 'content-type': 'application/x-ndjson' } },
  );
}

describe('progress stream', () => {
  it('accepts source inspection progress before a final outcome', async () => {
    const received: AnalysisEvent[] = [];
    await consumeAnalysis(
      response([
        '{"event":"discovery_progress","data":{"agent":"connector","status":"blocked","message":"Missing income bins"}}\n{"event":"complete","data":{"status":"insufficient_data"}}',
      ]),
      (event) => received.push(event),
    );
    expect(received[0].event).toBe('discovery_progress');
  });
  it('handles events split across chunks and a final line without newline', async () => {
    const received: AnalysisEvent[] = [];
    await consumeAnalysis(
      response([
        '{"event":"down',
        'loading","data":{"message":"Vérification"}}\n',
        '{"event":"complete","data":{"status":"insufficient_data"}}',
      ]),
      (event) => received.push(event),
    );
    expect(received.map((e) => e.event)).toEqual(['downloading', 'complete']);
  });
  it('reports an interrupted stream instead of success', async () => {
    await expect(
      consumeAnalysis(response(['{"event":"downloading","data":{}}\n']), () => undefined),
    ).rejects.toThrow('interrompue');
  });
  it('rejects malformed provider events', async () => {
    await expect(
      consumeAnalysis(response(['{"event":"fake_score","data":{}}\n']), () => undefined),
    ).rejects.toThrow('invalide');
  });
  it('preserves a useful server error', async () => {
    await expect(
      consumeAnalysis(Response.json({ detail: 'Provider busy' }, { status: 429 }), () => undefined),
    ).rejects.toThrow('Provider busy');
  });
  it('rejects data after completion', async () => {
    await expect(
      consumeAnalysis(
        response([
          '{"event":"complete","data":{"status":"measured"}}\n{"event":"downloading","data":{}}',
        ]),
        () => undefined,
      ),
    ).rejects.toThrow('après la fin');
  });
});
