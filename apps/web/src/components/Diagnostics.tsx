import type { Diagnostic } from '@/lib/types';
import { t } from '@/lib/i18n';

export default function Diagnostics({
  diagnostic,
  failed,
}: {
  diagnostic: Diagnostic;
  failed?: boolean;
}) {
  return (
    <section className="diagnostics" aria-label="Diagnostic de disponibilité">
      <span className="diagnostic-icon" aria-hidden="true">
        i
      </span>
      <h3>{failed ? 'L’analyse n’a pas pu être terminée' : t.insufficient}</h3>
      <p>{diagnostic.reason}</p>
      {diagnostic.web_discovery && (
        <p className="notice">
          {diagnostic.web_discovery.status === 'completed'
            ? 'Des pistes ont été recherchées sur le Web. Leur présence ne garantit pas une analyse exploitable.'
            : diagnostic.web_discovery.status === 'partial'
              ? 'Des pistes ont été trouvées sur le Web. Le modèle IA est indisponible ; une inspection limitée sans IA a pris le relais.'
              : diagnostic.web_discovery.status === 'not_configured'
                ? 'La recherche Web élargie n’est pas activée sur ce serveur. La vérification couvre les catalogues déjà intégrés.'
                : 'La recherche Web a échoué ou a atteint sa limite. Cela ne signifie pas que les données n’existent pas.'}
        </p>
      )}
      {diagnostic.availability === 'integration_required' && (
        <p>
          Une configuration de connecteur a été proposée ; son intégration et sa validation restent
          nécessaires.
        </p>
      )}
      {diagnostic.ai_discovery === 'rate_limited' && (
        <p className="notice">
          Le modèle IA gratuit est temporairement limité. Les sources officielles ont tout de même
          été examinées.
        </p>
      )}
      {!!diagnostic.missing?.length && (
        <>
          <h4>Ce qu’il manque</h4>
          <ul>
            {diagnostic.missing.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
      {!!diagnostic.sources_attempted?.length && (
        <>
          <h4>Sources examinées</h4>
          <ul className="attempted-sources">
            {diagnostic.sources_attempted.map((source, i) => (
              <li key={i}>
                {source.url?.startsWith('https://') ? (
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.publisher} ↗
                  </a>
                ) : (
                  <strong>{source.publisher}</strong>
                )}
                {source.reason && <small>{source.reason}</small>}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="fine-print">
        Une absence de résultat n’est pas un indice nul. Elle ne démontre pas l’absence de
        ségrégation.
      </p>
    </section>
  );
}
