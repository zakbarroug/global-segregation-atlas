'use client';

import { useEffect, useId, useRef, useState } from 'react';
import { t } from '@/lib/i18n';
import type { Place } from '@/lib/types';

export function placeLabel(place: Place) {
  return [place.label, ...place.admin_labels, place.country].join(', ');
}

export default function CitySearch({ onSelect }: { onSelect: (place: Place) => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);
  const [active, setActive] = useState(-1);
  const selectedQuery = useRef('');
  const root = useRef<HTMLDivElement>(null);
  const id = useId();

  useEffect(() => {
    if (query.trim().length < 2 || query === selectedQuery.current) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setBusy(true);
      setError('');
      setSearched(false);
      setResults([]);
      setActive(-1);
      try {
        const response = await fetch(`/api/places/search?q=${encodeURIComponent(query)}`, {
          signal: controller.signal,
          cache: 'no-store',
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || t.searchError);
        if (!controller.signal.aborted) {
          setResults(body.places);
          setSearched(true);
        }
      } catch (cause) {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : t.searchError);
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }, 650);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  useEffect(() => {
    const close = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);

  function choose(place: Place) {
    selectedQuery.current = place.label;
    setQuery(place.label);
    setOpen(false);
    setBusy(false);
    onSelect(place);
  }

  return (
    <div className="city-search" ref={root}>
      <label htmlFor={id} className="sr-only">
        {t.search}
      </label>
      <svg
        className="search-icon"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <circle cx="10.8" cy="10.8" r="6.8" stroke="currentColor" strokeWidth="1.7" />
        <path d="m16 16 4.5 4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      </svg>
      <input
        id={id}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open && query.length >= 2}
        aria-controls={`${id}-list`}
        aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
        placeholder={t.search}
        value={query}
        autoComplete="off"
        maxLength={120}
        onChange={(event) => {
          selectedQuery.current = '';
          setQuery(event.target.value);
          setOpen(true);
          setResults([]);
          setSearched(false);
          setError('');
          setBusy(false);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false);
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setOpen(true);
            setActive((i) => Math.min(i + 1, results.length - 1));
          }
          if (event.key === 'ArrowUp') {
            event.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          }
          if (event.key === 'Enter' && results[active]) {
            event.preventDefault();
            choose(results[active]);
          }
        }}
      />
      <span className="search-hint" aria-hidden="true">
        {busy ? '…' : '↵'}
      </span>
      {open && query.length >= 2 && (
        <div className="search-dropdown">
          <div role="status" className="search-status">
            {busy
              ? t.searching
              : error ||
                (searched && !results.length ? t.noResults : 'Villes · sélectionnez un résultat')}
          </div>
          <ul role="listbox" id={`${id}-list`} aria-label="Résultats de recherche">
            {results.map((place, index) => (
              <li
                role="option"
                aria-selected={index === active}
                key={`${place.provider}-${place.provider_id}`}
                id={`${id}-${index}`}
              >
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => choose(place)}
                  onMouseEnter={() => setActive(index)}
                >
                  <span className="country-code">{place.country_code}</span>
                  <span>
                    <strong>{place.label}</strong>
                    <small>{[...place.admin_labels, place.country].join(' · ')}</small>
                  </span>
                  <span className="search-arrow">↗</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="search-credit">Répertoire mondial · GeoNames / OpenStreetMap</div>
        </div>
      )}
    </div>
  );
}
