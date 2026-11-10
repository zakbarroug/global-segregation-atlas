import type { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const route = path.join('/');
  const allowed =
    request.method === 'POST'
      ? route === 'analysis'
      : ['places/search', 'providers', 'health'].includes(route);
  if (!allowed) return Response.json({ detail: 'Not found' }, { status: 404 });
  const url = new URL(`/${route}`, process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000');
  if (route === 'places/search')
    url.searchParams.set('q', request.nextUrl.searchParams.get('q') || '');
  let body: string | undefined;
  if (request.method === 'POST') {
    const reader = request.body?.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (!reader) return Response.json({ detail: 'Missing body' }, { status: 400 });
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > 16384) {
          await reader.cancel();
          return Response.json({ detail: 'Request too large' }, { status: 413 });
        }
        chunks.push(value);
      }
      body = Buffer.concat(chunks).toString('utf8');
    } finally {
      reader.releaseLock();
    }
  }
  try {
    const response = await fetch(url, {
      method: request.method,
      body,
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      signal: request.signal,
    });
    return new Response(response.body, {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') || 'application/json',
        'Cache-Control': 'no-store',
        'X-Accel-Buffering': 'no',
      },
    });
  } catch {
    return Response.json(
      { detail: 'Le service d’analyse est inaccessible. Vérifiez que FastAPI fonctionne.' },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST };
