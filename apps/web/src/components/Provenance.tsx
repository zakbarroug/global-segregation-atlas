import type { Source } from '@/lib/types';

export default function Provenance({ sources }: { sources: Source[] }) {
  return (
    <div className="provenance-list">
      {sources.map((source, i) => (
        <article key={`${source.url}-${i}`}>
          <div className="source-mark">{String(i + 1).padStart(2, '0')}</div>
          <div>
            <h4>{source.publisher}</h4>
            <p>{source.title}</p>
            {source.url?.startsWith('https://') && (
              <a href={source.url} target="_blank" rel="noreferrer">
                Consulter la source officielle ↗
              </a>
            )}
            <dl>
              {source.year && (
                <>
                  <dt>Millésime</dt>
                  <dd>{source.year}</dd>
                </>
              )}
              {source.geographic_unit && (
                <>
                  <dt>Unité</dt>
                  <dd>{source.geographic_unit}</dd>
                </>
              )}
              {source.license && (
                <>
                  <dt>Réutilisation</dt>
                  <dd>
                    {source.license_url ? (
                      <a href={source.license_url} target="_blank" rel="noreferrer">
                        {source.license}
                      </a>
                    ) : (
                      source.license
                    )}
                  </dd>
                </>
              )}
              {source.retrieval_timestamp && (
                <>
                  <dt>Consultée</dt>
                  <dd>{new Date(source.retrieval_timestamp).toLocaleString('fr-FR')}</dd>
                </>
              )}
            </dl>
            {source.citation && <p className="citation">{source.citation}</p>}
          </div>
        </article>
      ))}
    </div>
  );
}
