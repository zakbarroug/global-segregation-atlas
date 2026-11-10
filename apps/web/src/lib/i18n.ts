// All navigation and workflow labels have a parallel vocabulary. French is the MVP locale.
export const messages = {
  fr: {
    search: 'Choisissez une ville du monde',
    searchHint: 'Ville, région ou pays',
    noResults: 'Aucune ville trouvée. Essayez un autre nom ou ajoutez le pays.',
    searchError: 'La recherche est indisponible. Réessayez dans un instant.',
    insufficient:
      'Impossible de calculer la ségrégation résidentielle à partir des données publiques trouvées pour cette ville',
    lowShare: 'Ménages à bas revenu',
    highShare: 'Ménages à haut revenu',
    methodology: 'Méthodologie',
    sources: 'Sources & qualité',
    export: 'Exporter la session',
    searching: 'Recherche mondiale…',
  },
  en: {
    search: 'Choose a city anywhere in the world',
    searchHint: 'City, region or country',
    noResults: 'No city found. Try another name or add the country.',
    searchError: 'Search is unavailable. Please try again shortly.',
    insufficient:
      'Residential segregation cannot be calculated from the public data found for this city',
    lowShare: 'Lower-income households',
    highShare: 'Higher-income households',
    methodology: 'Methodology',
    sources: 'Sources & quality',
    export: 'Export this session',
    searching: 'Searching worldwide…',
  },
};
export const t = messages.fr;
export const number = (value: number) => new Intl.NumberFormat('fr-FR').format(value);
export const percent = (value: number | null) =>
  value === null
    ? 'Non disponible'
    : new Intl.NumberFormat('fr-FR', { style: 'percent', maximumFractionDigits: 1 }).format(value);
