import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import Diagnostics from '../src/components/Diagnostics';
import DiscoveryActivity from '../src/components/DiscoveryActivity';
import MetricCards from '../src/components/MetricCards';
import { placeLabel } from '../src/components/CitySearch';
import { csvCell } from '../src/lib/export';
import type { Metric, Place } from '../src/lib/types';

describe('honest empty states', () => {
  it('distinguishes an unavailable search engine from missing city data', () => {
    render(
      <Diagnostics
        diagnostic={{
          reason: 'Distribution non vérifiée',
          web_discovery: { status: 'not_configured', reason: 'No search engine' },
          availability: 'integration_required',
        }}
      />,
    );
    expect(screen.getByText(/recherche Web élargie n’est pas activée/)).toBeInTheDocument();
    expect(
      screen.getByText(/intégration et sa validation restent nécessaires/),
    ).toBeInTheDocument();
  });
  it('explains the free model limit without claiming measured data', () => {
    render(
      <Diagnostics
        diagnostic={{ reason: 'Sources still incomplete', ai_discovery: 'rate_limited' }}
      />,
    );
    expect(screen.getByText(/modèle IA gratuit est temporairement limité/)).toBeInTheDocument();
  });
  it('distinguishes a configured connector from validated observations', () => {
    render(
      <DiscoveryActivity
        entries={[
          {
            agent: 'connector',
            status: 'configured',
            message: 'Limites vérifiées',
            report: { template: 'census', status: 'configured', activated: true },
          },
        ]}
      />,
    );
    expect(screen.getByText(/validation des données requise/)).toBeInTheDocument();
  });
  it('explains that insufficient data is not zero segregation', () => {
    render(
      <Diagnostics
        diagnostic={{
          reason: 'Only median incomes available',
          missing: ['Household counts by income bracket'],
        }}
      />,
    );
    expect(screen.getByText(/Impossible de calculer/)).toBeInTheDocument();
    expect(screen.getByText(/n’est pas un indice nul/)).toBeInTheDocument();
    expect(screen.getByText('Household counts by income bracket')).toBeInTheDocument();
  });
  it('does not render a zero value for an unavailable metric', () => {
    const metric: Metric = {
      id: 'dissimilarity',
      label: 'Dissimilarité',
      value: null,
      definition: 'D',
      interpretation: '',
      target_groups: '',
      unavailable_reason: 'Zero low-income group',
      warnings: [],
      input_coverage: {},
    };
    render(<MetricCards metrics={[metric]} />);
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.queryByText('0,000')).not.toBeInTheDocument();
    expect(screen.getByText('Zero low-income group')).toBeInTheDocument();
  });
});

it('disambiguates cities by country and administrative region', () => {
  const base = { label: 'Vienne', admin_labels: ['Wien'], country: 'Autriche' } as Place;
  const other = { ...base, admin_labels: ['Isère'], country: 'France' };
  expect(placeLabel(base)).toBe('Vienne, Wien, Autriche');
  expect(placeLabel(base)).not.toBe(placeLabel(other));
});

it('escapes quotes and protects CSV formula execution', () => {
  expect(csvCell('=HYPERLINK("x")')).toBe('"\'=HYPERLINK(""x"")"');
  expect(csvCell('Sector "A"')).toBe('"Sector ""A"""');
});
