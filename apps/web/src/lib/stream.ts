import type { AnalysisEvent } from './types';

const EVENTS = new Set([
  'started',
  'geography_ready',
  'source_found',
  'discovery_progress',
  'downloading',
  'validating',
  'metric_computed',
  'map_ready',
  'insufficient_data',
  'failed',
  'complete',
]);

export async function consumeAnalysis(response: Response, onEvent: (event: AnalysisEvent) => void) {
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Erreur HTTP ${response.status}`);
  }
  if (!response.body || !response.headers.get('content-type')?.includes('application/x-ndjson')) {
    throw new Error('Le serveur n’a pas renvoyé de flux d’analyse valide.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '';
  let bytes = 0;
  let complete = false;
  function parse(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line);
    if (!EVENTS.has(event.event) || !event.data || typeof event.data !== 'object')
      throw new Error('Événement d’analyse invalide.');
    if (complete) throw new Error('Le serveur a envoyé des données après la fin de l’analyse.');
    onEvent(event as AnalysisEvent);
    if (event.event === 'complete') complete = true;
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > 20_000_000)
        throw new Error('La réponse dépasse la limite de mémoire de cette session.');
      buffer += decoder.decode(value, { stream: true });
      let end: number;
      while ((end = buffer.indexOf('\n')) !== -1) {
        parse(buffer.slice(0, end));
        buffer = buffer.slice(end + 1);
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) parse(buffer);
    if (!complete)
      throw new Error(
        'Analyse interrompue avant sa fin. Les résultats visibles sont partiels ; vous pouvez réessayer.',
      );
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
