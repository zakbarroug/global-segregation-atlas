import type { MapResult, Metric, Place } from './types';

function download(content: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function csvCell(value: unknown): string {
  let text = String(value ?? '');
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`; // Spreadsheet formula injection protection.
  return `"${text.replaceAll('"', '""')}"`;
}

export function exportSession(
  result: MapResult,
  place: Place,
  metrics: Metric[],
  format: 'geojson' | 'csv',
) {
  if (!result.export_allowed) return;
  const name = `atlas-${place.country_code}-${result.year}`;
  if (format === 'geojson') {
    download(
      JSON.stringify({
        ...result.geojson,
        atlas: {
          place,
          year: result.year,
          income: result.income,
          metrics,
          sources: result.sources,
          warnings: result.warnings,
          coverage: result.coverage,
        },
      }),
      `${name}.geojson`,
      'application/geo+json',
    );
  } else {
    const columns = [
      'area_id',
      'name',
      'households',
      'low_share',
      'high_share',
      'total_moe_90',
      ...result.income.bins.map((b) => b.variable),
      ...result.income.bins.map((b) => b.variable.replace(/E$/, 'M')),
    ];
    const rows = result.geojson.features.map(({ properties: p }) => [
      p.area_id,
      p.name,
      p.households,
      p.low_share,
      p.high_share,
      p.total_moe_90,
      ...p.income_counts,
      ...p.income_moe_90,
    ]);
    download(
      [columns, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n'),
      `${name}.csv`,
      'text/csv;charset=utf-8',
    );
  }
}
