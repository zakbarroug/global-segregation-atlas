import type { Metric } from '@/lib/types';

const EXPLANATIONS: Record<string, string> = {
  dissimilarity: 'Répartition des ménages à bas et haut revenu. De 0 (identique) à 1 (séparée).',
  isolation: 'Part de ménages à bas revenu dans le secteur d’un ménage à bas revenu typique.',
  exposure: 'Part de ménages à haut revenu dans le secteur d’un ménage à bas revenu typique.',
  theil_h: 'Part de la diversité des 16 catégories de revenu liée aux différences entre secteurs.',
  rank_order_h:
    'Estimation selon l’ordre des revenus groupés, calculée par la méthode de référence PySAL.',
};
const SYMBOLS: Record<string, string> = {
  dissimilarity: 'D',
  isolation: 'P*',
  exposure: 'P↗',
  theil_h: 'H',
  rank_order_h: 'Hᴿ',
};

export default function MetricCards({ metrics }: { metrics: Metric[] }) {
  return (
    <div className="metric-grid">
      {metrics.map((metric) => (
        <article className="metric-card" key={metric.id}>
          <div className="metric-top">
            <span>{metric.label}</span>
            <span className="metric-symbol">{SYMBOLS[metric.id]}</span>
          </div>
          <strong className="metric-value">
            {metric.value === null
              ? '—'
              : metric.value.toLocaleString('fr-FR', {
                  minimumFractionDigits: 3,
                  maximumFractionDigits: 3,
                })}
          </strong>
          <p>{metric.value === null ? metric.unavailable_reason : EXPLANATIONS[metric.id]}</p>
          <details>
            <summary>Définition</summary>
            <code>{metric.definition}</code>
            <p>{metric.target_groups}</p>
          </details>
        </article>
      ))}
    </div>
  );
}
