'use client';

import dynamic from 'next/dynamic';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import type { FeatureCollection } from 'geojson';
import CitySearch from './CitySearch';
import MetricCards from './MetricCards';
import Diagnostics from './Diagnostics';
import Provenance from './Provenance';
import DiscoveryActivity from './DiscoveryActivity';
import { consumeAnalysis } from '@/lib/stream';
import { exportSession } from '@/lib/export';
import { number, percent, t } from '@/lib/i18n';
import type {
  AreaProperties,
  Diagnostic,
  DiscoveryProgress,
  Indicator,
  MapResult,
  Metric,
  Place,
  Source,
} from '@/lib/types';

const AtlasMap = dynamic(() => import('./AtlasMap'), {
  ssr: false,
  loading: () => <div className="map-loading">Chargement de la carte…</div>,
});
type Status = 'idle' | 'running' | 'measured' | 'insufficient_data' | 'failed' | 'cancelled';

export default function Atlas({ styleUrl }: { styleUrl: string }) {
  const [place, setPlace] = useState<Place | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const [stage, setStage] = useState('');
  const [stageIndex, setStageIndex] = useState(0);
  const [boundary, setBoundary] = useState<FeatureCollection | null>(null);
  const [extent, setExtent] = useState('');
  const [result, setResult] = useState<MapResult | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [diagnostic, setDiagnostic] = useState<Diagnostic | null>(null);
  const [discovery, setDiscovery] = useState<DiscoveryProgress[]>([]);
  const [indicator, setIndicator] = useState<Indicator>('low_share');
  const [area, setArea] = useState<AreaProperties | null>(null);
  const [tab, setTab] = useState<'method' | 'sources' | 'export'>('method');
  const [year, setYear] = useState(2024);
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => current.current?.abort(), []);

  async function analyze(selected: Place, selectedYear = year) {
    current.current?.abort();
    const controller = new AbortController();
    current.current = controller;
    setPlace(selected);
    setStatus('running');
    setStage('Identification des sources');
    setStageIndex(0);
    setBoundary(null);
    setResult(null);
    setMetrics([]);
    setSources([]);
    setDiagnostic(null);
    setDiscovery([]);
    setArea(null);
    setExtent('Point du répertoire mondial ; limite municipale non vérifiée');
    try {
      const response = await fetch('/api/analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ city_id: selected.city_id, requested_year: selectedYear }),
        signal: controller.signal,
      });
      await consumeAnalysis(response, (event) => {
        if (controller.signal.aborted) return;
        switch (event.event) {
          case 'geography_ready':
            setBoundary(event.data.boundary);
            setExtent(event.data.extent_description);
            break;
          case 'source_found':
            setSources((old) => [...old, event.data.source]);
            break;
          case 'discovery_progress':
            setStage(event.data.message);
            setDiscovery((old) => [...old.slice(-9), event.data]);
            break;
          case 'downloading':
            setStage(event.data.message);
            setStageIndex(1);
            break;
          case 'validating':
            setStage(event.data.message);
            setStageIndex(2);
            break;
          case 'map_ready':
            setResult(event.data);
            setSources(event.data.sources);
            setStage('Carte validée · calcul des indices');
            setStageIndex(3);
            break;
          case 'metric_computed':
            setMetrics((old) => [
              ...old.filter((m) => m.id !== event.data.metric.id),
              event.data.metric,
            ]);
            break;
          case 'insufficient_data':
          case 'failed':
            setDiagnostic(event.data);
            setStatus(event.event);
            break;
          case 'complete':
            setStatus(event.data.status);
            setStage(event.data.message || 'Analyse terminée');
            setStageIndex(4);
            break;
        }
      });
    } catch (cause) {
      if (!controller.signal.aborted) {
        setStatus('failed');
        setDiagnostic({
          reason:
            cause instanceof Error ? cause.message : 'Erreur de connexion au service d’analyse.',
        });
      }
    }
  }

  function cancel() {
    current.current?.abort();
    setStatus('cancelled');
    setStage('Analyse annulée. Les éventuels résultats affichés sont partiels.');
  }
  const busy = status === 'running';
  const isPartial = !!result && !['running', 'measured'].includes(status);

  return (
    <div className="atlas-app">
      <header className="topbar">
        <Link className="brand" href="/" aria-label="Global Segregation Atlas, accueil">
          <span className="brand-globe" aria-hidden="true">
            ◎
          </span>
          <span>
            GLOBAL SEGREGATION
            <span className="brand-sub">
              ATLAS <span>Observatoire des territoires</span>
            </span>
          </span>
        </Link>
        <nav aria-label="Navigation principale">
          <a href="#explorer" className="nav-active">
            Explorer
          </a>
          <a href="#methodologie" onClick={() => setTab('method')}>
            Comprendre les indices
          </a>
        </nav>
        <div className="privacy-pill">
          <span />
          Sans stockage de données
        </div>
      </header>

      <main id="explorer">
        <section className="intro">
          <div>
            <div className="eyebrow">UNE AUTRE LECTURE DES TERRITOIRES</div>
            <h1>Les revenus dessinent la ville.</h1>
            <p>Explorez la ségrégation résidentielle à partir de données publiques officielles.</p>
          </div>
          <div className="search-block">
            <CitySearch onSelect={(selected) => void analyze(selected)} />
            <p>Recherche mondiale. Mesure uniquement lorsque les données le permettent.</p>
          </div>
        </section>

        <div className="workspace">
          <aside className="analysis-panel" aria-label="Analyse de la ville">
            <div className="panel-top">
              <span className="eyebrow">TERRITOIRE À L’ÉTUDE</span>
              <span className={`status-badge ${status}`}>
                {busy
                  ? 'En cours'
                  : status === 'measured'
                    ? 'Mesuré'
                    : status === 'insufficient_data'
                      ? 'Non mesurable'
                      : status === 'failed'
                        ? 'Interrompu'
                        : status === 'cancelled'
                          ? 'Annulé'
                          : 'À explorer'}
              </span>
            </div>
            <h2>{place?.label || 'Un monde à explorer'}</h2>
            <p className="place-subtitle">
              {place
                ? `${place.country} · ${place.country_code}`
                : 'Chaque ville raconte une distribution différente.'}
            </p>
            {place ? (
              <>
                <div className="year-row">
                  <label htmlFor="year">Millésime demandé</label>
                  <select
                    id="year"
                    value={year}
                    disabled={busy}
                    onChange={(e) => setYear(Number(e.target.value))}
                  >
                    {[2024, 2023, 2022, 2021].map((y) => (
                      <option value={y} key={y}>
                        {y}
                      </option>
                    ))}
                  </select>
                  <button
                    className="icon-button"
                    disabled={busy}
                    onClick={() => void analyze(place)}
                    title="Relancer l’analyse"
                    aria-label="Relancer l’analyse"
                  >
                    ↻
                  </button>
                </div>
                <p className="extent-note">{extent}</p>
                {sources.some((source) => source.id === 'us_acs_b19001') && (
                  <p className="census-notice">
                    This product uses the Census Bureau Data API but is not endorsed or certified by
                    the Census Bureau.
                  </p>
                )}
              </>
            ) : (
              <div className="welcome-card">
                <span className="line-icon" aria-hidden="true">
                  ⌖
                </span>
                <h3>Commencez par un lieu</h3>
                <p>
                  Recherchez une ville, puis sélectionnez le bon pays. La carte s’ouvre
                  immédiatement, les sources sont vérifiées en direct.
                </p>
                <div className="steps-intro">
                  <span>
                    01 <b>Choisir</b>
                  </span>
                  <span>
                    02 <b>Vérifier</b>
                  </span>
                  <span>
                    03 <b>Comprendre</b>
                  </span>
                </div>
              </div>
            )}

            {busy && (
              <div className="progress-box" role="status" aria-live="polite">
                <div>
                  <span className="spinner" />
                  <strong>{stage}</strong>
                  <button onClick={cancel} aria-label="Annuler l’analyse">
                    ×
                  </button>
                </div>
                <div className="progress-track">
                  {['Sources', 'Données', 'Validation', 'Calcul'].map((s, i) => (
                    <span key={s} className={i <= stageIndex ? 'done' : ''} title={s} />
                  ))}
                </div>
                <p>Les données sont téléchargées à la demande. Le délai dépend des fournisseurs.</p>
              </div>
            )}
            {status === 'cancelled' && (
              <p className="notice" role="status">
                {stage}
              </p>
            )}
            {diagnostic && <Diagnostics diagnostic={diagnostic} failed={status === 'failed'} />}
            {!!discovery.length && <DiscoveryActivity entries={discovery} />}
            {result && (
              <>
                {isPartial && (
                  <p className="notice">Résultats partiels : l’analyse n’a pas été terminée.</p>
                )}
                <div className="coverage-grid">
                  <div>
                    <strong>{number(result.coverage.households)}</strong>
                    <span>ménages estimés</span>
                  </div>
                  <div>
                    <strong>{number(result.coverage.areas)}</strong>
                    <span>census tracts</span>
                  </div>
                </div>
                <div className="section-label">
                  INDICES À L’ÉCHELLE DE LA VILLE <span>0 — 1</span>
                </div>
                <MetricCards metrics={metrics} />
                <p className="fine-print">
                  Les indices décrivent une répartition spatiale. Ils ne mesurent ni la pauvreté, ni
                  ses causes.
                </p>
                <div className="income-definition">
                  <span className="eyebrow">REVENU ÉTUDIÉ</span>
                  <h3>Ménages · avant impôts</h3>
                  <p>
                    {result.income.reference_period} · {result.income.price_basis}
                  </p>
                  <div>
                    <span className="income-dot low" />
                    Bas revenu : moins de 35 000 $ / an
                  </div>
                  <div>
                    <span className="income-dot high" />
                    Haut revenu : au moins 100 000 $ / an
                  </div>
                  <p className="fine-print">
                    Ces seuils fixes ne sont pas les quartiles. Les revenus intermédiaires sont
                    exclus de D.
                  </p>
                </div>
              </>
            )}
            {!result && !busy && (
              <div className="integrity-note">
                <span aria-hidden="true">◇</span>
                <p>
                  Pas de score sans données valides.
                  <br />
                  <strong>Les lacunes restent visibles.</strong>
                </p>
              </div>
            )}
          </aside>

          <section className="map-panel" aria-label="Exploration cartographique">
            <AtlasMap
              styleUrl={styleUrl}
              place={place}
              areas={result?.geojson || null}
              boundary={boundary}
              indicator={indicator}
              onArea={setArea}
            />
            <div className="map-context">
              <span className="live-dot" />
              <span>{place ? `${place.label} · ${place.country_code}` : 'Vue mondiale'}</span>
              <span className="context-divider" />
              {result ? `ACS ${result.year}` : 'Fond de carte'}
            </div>
            {!place && (
              <div className="map-welcome">
                <span className="eyebrow">LE MONDE, VILLE PAR VILLE</span>
                <h2>
                  Des lieux.
                  <br />
                  Des revenus.
                  <br />
                  <em>Des perspectives.</em>
                </h2>
                <p>
                  Choisissez une ville pour commencer
                  <br />
                  une analyse sans données préchargées.
                </p>
              </div>
            )}
            {result && (
              <div className="legend">
                <div className="legend-top">
                  <span className="eyebrow">COULEUR DES SECTEURS</span>
                  <span>PART DES MÉNAGES</span>
                </div>
                <label className="sr-only" htmlFor="indicator">
                  Indicateur cartographique
                </label>
                <select
                  id="indicator"
                  value={indicator}
                  onChange={(e) => setIndicator(e.target.value as Indicator)}
                >
                  <option value="low_share">{t.lowShare} · &lt; 35 000 $</option>
                  <option value="high_share">{t.highShare} · ≥ 100 000 $</option>
                </select>
                <div className="legend-gradient" />
                <div className="legend-values">
                  <span>0 %</span>
                  <span>50 %</span>
                  <span>100 %</span>
                </div>
                <p>Gris : aucun ménage. La couleur représente une part locale, pas l’indice D.</p>
              </div>
            )}
            {place && !result && !busy && (
              <div className="map-caption">
                Localisation vérifiée · aucune donnée de revenu affichée
              </div>
            )}
            {area && result && (
              <div className="area-card" aria-live="polite">
                <button
                  className="close-area"
                  onClick={() => setArea(null)}
                  aria-label="Fermer le détail du secteur"
                >
                  ×
                </button>
                <span className="eyebrow">SECTEUR SÉLECTIONNÉ</span>
                <h3>{area.name.split(';')[0]}</h3>
                <p className="area-code">GEOID {area.area_id}</p>
                <div>
                  <strong>{percent(area[indicator])}</strong>
                  <span>{indicator === 'low_share' ? t.lowShare : t.highShare}</span>
                </div>
                <p>
                  {number(area.households)} ménages estimés
                  {area.total_moe_90 !== null ? ` · ± ${number(area.total_moe_90)} (90 %)` : ''}
                </p>
              </div>
            )}
          </section>
        </div>

        {result && (
          <section className="accessible-areas">
            <label htmlFor="area-picker">Inspecter un secteur sans utiliser la carte</label>
            <select
              id="area-picker"
              value={area?.area_id || ''}
              onChange={(e) =>
                setArea(
                  result.geojson.features.find((f) => f.properties.area_id === e.target.value)
                    ?.properties || null,
                )
              }
            >
              <option value="">Choisissez un census tract</option>
              {result.geojson.features.map((f) => (
                <option key={f.properties.area_id} value={f.properties.area_id}>
                  {f.properties.name} · {percent(f.properties[indicator])}
                </option>
              ))}
            </select>
          </section>
        )}

        <section className="details-section" id="methodologie">
          <div className="detail-tabs" role="tablist" aria-label="Comprendre cette analyse">
            {(
              [
                { id: 'method', label: t.methodology },
                { id: 'sources', label: t.sources },
                { id: 'export', label: t.export },
              ] as const
            ).map((item) => (
              <button
                key={item.id}
                id={`tab-${item.id}`}
                role="tab"
                aria-selected={tab === item.id}
                aria-controls={`panel-${item.id}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
                {item.id === 'sources' && !!sources.length && <span>{sources.length}</span>}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id={`panel-${tab}`}
            aria-labelledby={`tab-${tab}`}
            className="detail-content"
          >
            {tab === 'method' && (
              <div className="method-grid">
                <div>
                  <span className="eyebrow">COMPRENDRE CE QUE L’ON MESURE</span>
                  <h2>
                    Une carte locale.
                    <br />
                    Des indices pour la ville.
                  </h2>
                  <p>
                    La carte montre la proportion de ménages d’un groupe de revenu dans chaque
                    secteur. Les indices résument les différences de répartition entre tous les
                    secteurs de la ville.
                  </p>
                </div>
                <div className="method-rules">
                  <article>
                    <span>01</span>
                    <div>
                      <h3>Des ménages, pas des moyennes</h3>
                      <p>
                        Il faut des effectifs par tranche de revenu. Un revenu médian par quartier
                        ne permet pas de calculer ces indices.
                      </p>
                    </div>
                  </article>
                  <article>
                    <span>02</span>
                    <div>
                      <h3>Le même territoire, le même millésime</h3>
                      <p>
                        Les effectifs et les polygones sont reliés par identifiant officiel. Les
                        jointures incomplètes et les millésimes incompatibles sont refusés.
                      </p>
                    </div>
                  </article>
                  <article>
                    <span>03</span>
                    <div>
                      <h3>Des limites qui accompagnent le résultat</h3>
                      <p>
                        Échantillonnage, taille des secteurs et définition du revenu influencent la
                        mesure. Les villes ne sont pas directement comparables entre pays.
                      </p>
                    </div>
                  </article>
                </div>
              </div>
            )}
            {tab === 'sources' && (
              <>
                {sources.length ? (
                  <Provenance sources={sources} />
                ) : (
                  <p className="empty-detail">
                    Les sources apparaîtront au cours de l’analyse d’une ville. Aucune observation
                    n’est préchargée.
                  </p>
                )}
                {result && (
                  <div className="quality-report">
                    <h3>Couverture de la jointure : {percent(result.coverage.fraction)}</h3>
                    <ul>
                      {result.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                    <details>
                      <summary>Composition des revenus · 16 tranches officielles</summary>
                      <table>
                        <thead>
                          <tr>
                            <th>Tranche annuelle</th>
                            <th>Ménages estimés</th>
                            <th>Part</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.income.bins.map((bin, i) => (
                            <tr key={bin.variable}>
                              <td>{bin.label}</td>
                              <td>{number(result.composition[i])}</td>
                              <td>{percent(result.composition[i] / result.coverage.households)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </details>
                  </div>
                )}
              </>
            )}
            {tab === 'export' && (
              <div className="export-panel">
                <div>
                  <h2>Emportez votre analyse.</h2>
                  <p>
                    Les fichiers sont créés dans votre navigateur à partir de la session ouverte. Le
                    serveur ne conserve ni les données, ni les cartes.
                  </p>
                  <p className="fine-print">
                    GeoJSON : géométries simplifiées, effectifs, marges d’erreur, indices et
                    provenance. CSV : effectifs et marges d’erreur par secteur. Les deux exports
                    utilisent les données Census du domaine public.
                  </p>
                </div>
                <div className="export-actions">
                  <button
                    disabled={!result?.export_allowed || !place || status !== 'measured'}
                    onClick={() =>
                      result && place && exportSession(result, place, metrics, 'geojson')
                    }
                  >
                    ↓ Télécharger GeoJSON
                  </button>
                  <button
                    className="secondary"
                    disabled={!result?.export_allowed || !place || status !== 'measured'}
                    onClick={() => result && place && exportSession(result, place, metrics, 'csv')}
                  >
                    ↓ Télécharger CSV
                  </button>
                  {status !== 'measured' && (
                    <small>Disponible après une analyse complète et validée.</small>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>
      </main>
      <footer>
        <div>
          <strong>Global Segregation Atlas</strong>
          <span>La transparence fait partie de la mesure.</span>
        </div>
        <p>
          Données d’analyse uniquement en mémoire. Les fournisseurs tiers peuvent conserver leurs
          propres journaux.{' '}
          {styleUrl
            ? 'Fond de carte selon attribution.'
            : 'Fond OSM et recherche Photon : usage modéré de développement.'}
        </p>
        <span className="footer-locale">FR · MVP</span>
      </footer>
    </div>
  );
}
