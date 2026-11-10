import type { DiscoveryProgress } from '@/lib/types';

export default function DiscoveryActivity({ entries }: { entries: DiscoveryProgress[] }) {
  return (
    <details className="discovery-activity">
      <summary>Vérification des sources · {entries.length} étapes</summary>
      <ol>
        {entries.map((entry, index) => (
          <li key={index}>
            <strong>{entry.message}</strong>
            {entry.report?.checks?.map((check) => (
              <p key={check}>{check}</p>
            ))}
            {entry.report?.activated && (
              <span>Source raccordée · validation des données requise</span>
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}
