'use client';

import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { GeoJSONSource, StyleSpecification } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import type { AreaProperties, Areas, Indicator, Place } from '@/lib/types';
import { percent } from '@/lib/i18n';

// MapLibre 6 is ESM-only. Explicitly emit its worker in the Next/Turbopack asset graph.
maplibregl.setWorkerUrl(
  new URL('maplibre-gl/dist/maplibre-gl-worker.mjs', import.meta.url).toString(),
);

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };
const baseStyle: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#e8edf0' } },
    {
      id: 'osm',
      type: 'raster',
      source: 'osm',
      paint: { 'raster-saturation': -0.85, 'raster-opacity': 0.88 },
    },
  ],
};

type Props = {
  place: Place | null;
  areas: Areas | null;
  boundary: FeatureCollection | null;
  indicator: Indicator;
  styleUrl: string;
  onArea: (area: AreaProperties) => void;
};

export default function AtlasMap({ place, areas, boundary, indicator, styleUrl, onArea }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const onAreaRef = useRef(onArea);
  const indicatorRef = useRef(indicator);
  const [ready, setReady] = useState(0);
  const [error, setError] = useState('');
  useEffect(() => {
    onAreaRef.current = onArea;
    indicatorRef.current = indicator;
  }, [onArea, indicator]);

  useEffect(() => {
    if (!container.current) return;
    let instance: maplibregl.Map;
    try {
      instance = new maplibregl.Map({
        container: container.current,
        style: styleUrl || baseStyle,
        center: [5, 32],
        zoom: 1.6,
        minZoom: 1,
        maxZoom: 17,
        attributionControl: { compact: true },
      });
    } catch {
      // A useful accessible state if the browser has no WebGL support.
      queueMicrotask(() =>
        setError(
          'WebGL est indisponible. Les résultats et les exports restent accessibles dans les panneaux.',
        ),
      );
      return;
    }
    map.current = instance;
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    instance.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: '260px',
    });
    instance.on('load', () => {
      instance.addSource('city-boundary', { type: 'geojson', data: EMPTY });
      instance.addSource('income-areas', { type: 'geojson', data: EMPTY, promoteId: 'area_id' });
      instance.addLayer({
        id: 'income-fill',
        type: 'fill',
        source: 'income-areas',
        paint: { 'fill-color': '#2d7692', 'fill-opacity': 0.83 },
      });
      instance.addLayer({
        id: 'income-lines',
        type: 'line',
        source: 'income-areas',
        paint: { 'line-color': '#ffffff', 'line-width': 0.45, 'line-opacity': 0.6 },
      });
      instance.addLayer({
        id: 'boundary-line',
        type: 'line',
        source: 'city-boundary',
        paint: { 'line-color': '#143d50', 'line-width': 1.5, 'line-dasharray': [3, 2] },
      });
      setReady((generation) => generation + 1);
    });
    instance.on('mousemove', 'income-fill', (event) => {
      const properties = event.features?.[0]?.properties;
      if (!properties) return;
      instance.getCanvas().style.cursor = 'pointer';
      const content = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = properties.name;
      const value = document.createElement('p');
      value.textContent = `${indicatorRef.current === 'low_share' ? 'Bas revenu' : 'Haut revenu'} : ${percent(properties[indicatorRef.current] ?? null)}`;
      content.append(title, value);
      popup.setLngLat(event.lngLat).setDOMContent(content).addTo(instance);
    });
    instance.on('mouseleave', 'income-fill', () => {
      instance.getCanvas().style.cursor = '';
      popup.remove();
    });
    instance.on('click', 'income-fill', (event) => {
      const p = event.features?.[0]?.properties;
      if (p)
        onAreaRef.current({
          ...p,
          income_counts:
            typeof p.income_counts === 'string' ? JSON.parse(p.income_counts) : p.income_counts,
          income_moe_90:
            typeof p.income_moe_90 === 'string' ? JSON.parse(p.income_moe_90) : p.income_moe_90,
          quality_flags:
            typeof p.quality_flags === 'string' ? JSON.parse(p.quality_flags) : p.quality_flags,
        } as AreaProperties);
    });
    instance.on('error', (event) => {
      if (event.error)
        setError(
          'Le fond de carte est partiellement indisponible. Les données officielles restent indépendantes du fond de carte.',
        );
    });
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      popup.remove();
      instance.remove();
      map.current = null;
    };
  }, [styleUrl]);

  useEffect(() => {
    if (!map.current || !place) return;
    map.current.flyTo({
      center: [place.longitude, place.latitude],
      zoom: 10,
      duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1200,
    });
    const marker = new maplibregl.Marker({ color: '#163d50', scale: 0.8 })
      .setLngLat([place.longitude, place.latitude])
      .addTo(map.current);
    return () => {
      marker.remove();
    };
  }, [place, ready]);

  useEffect(() => {
    if (!ready || !map.current) return;
    (map.current.getSource('income-areas') as GeoJSONSource)?.setData(areas || EMPTY);
    (map.current.getSource('city-boundary') as GeoJSONSource)?.setData(boundary || EMPTY);
  }, [ready, areas, boundary]);

  useEffect(() => {
    if (!ready || !map.current) return;
    map.current.setPaintProperty('income-fill', 'fill-color', [
      'case',
      ['==', ['get', indicator], null],
      '#b6bec3',
      [
        'interpolate',
        ['linear'],
        ['get', indicator],
        0,
        '#ffffd9',
        0.25,
        '#c7e9b4',
        0.5,
        '#7fcdbb',
        0.75,
        '#2c7fb8',
        1,
        '#253494',
      ],
    ]);
  }, [ready, indicator]);

  return (
    <>
      <div
        ref={container}
        className="map-canvas"
        role="region"
        aria-label={
          place ? `Carte de ${place.label}, ${place.country}` : 'Carte du monde interactive'
        }
      />
      {error && (
        <div className="map-error" role="status">
          {error}
        </div>
      )}
    </>
  );
}
