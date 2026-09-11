import { useEffect, useMemo, useState } from 'react';
import { MapContainer, TileLayer, Polyline, Circle, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useTranslation } from '../hooks/useTranslation';

export interface RouteCircle {
  lat: number | null;
  lon: number | null;
  radius_km: number;
  label: string;
  location_id?: string;
  search_id?: number;
}

export interface RouteListingGeo {
  id: string;
  title: string;
  price: string;
  location: string;
  url: string;
  lat: number | null;
  lon: number | null;
  detour_min: number | null;
  offroute_km: number | null;
  // Why a detour is missing, which is not the same question as whether the
  // listing has coordinates: 'too_far' and 'failed' both have them.
  geo_status?: 'routed' | 'too_far' | 'unplaceable' | 'failed' | null;
  niceness_score: number | null;
  llm_processed?: boolean;
  images: string[];
}

interface RouteCorridorMapProps {
  polyline: [number, number][];
  circles: RouteCircle[];
  listings: RouteListingGeo[];
  selectedListingId: string | null;
  onSelectListing: (id: string) => void;
  originName?: string;
  destinationName?: string;
  className?: string;
}

// Automatically fit map view to the bounds of the route, circles, and listings
function MapBoundsFitter({ bounds }: { bounds: L.LatLngBounds | null }) {
  const map = useMap();
  useEffect(() => {
    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
    }
  }, [map, bounds]);
  return null;
}

// 8px dot for unselected listing with 32x32 touch target
function createDotIcon(detourMin: number | null) {
  const detourLabel = detourMin !== null ? (detourMin < 1 ? 'on route' : `+${Math.round(detourMin)}m`) : '';
  const html = `
    <div class="cursor-pointer -translate-x-1/2 -translate-y-1/2 flex items-center justify-center w-8 h-8 group" title="${detourLabel}">
      <div class="w-2 h-2 rounded-full bg-emerald-400 ring-2 ring-slate-950 shadow-md group-hover:scale-150 group-hover:bg-emerald-300 transition-all duration-150"></div>
    </div>
  `;
  return L.divIcon({
    html,
    className: 'prism-listing-marker-dot',
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

// Selected or hovered listing: full pill with minutes
function createSelectedPillIcon(detourMin: number | null) {
  const detourText = detourMin !== null ? (detourMin < 1 ? 'on route' : `+${Math.round(detourMin)}m`) : '•';
  const html = `
    <div class="cursor-pointer -translate-x-1/2 -translate-y-1/2 flex items-center justify-center z-50">
      <div class="px-2.5 py-1 rounded-full text-xs font-mono shadow-2xl flex items-center gap-1.5 whitespace-nowrap bg-emerald-400 text-slate-950 ring-4 ring-emerald-400/40 font-extrabold">
        <span class="w-1.5 h-1.5 rounded-full bg-slate-950"></span>
        <span>${detourText}</span>
      </div>
    </div>
  `;
  return L.divIcon({
    html,
    className: 'prism-listing-marker-pill',
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

// Cluster marker showing count for overlapping listings
function createClusterIcon(count: number) {
  const size = count >= 10 ? 'w-7 h-7 text-xs' : 'w-6 h-6 text-2xs';
  const html = `
    <div class="cursor-pointer -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
      <div class="${size} rounded-full bg-emerald-600 text-white font-mono font-bold shadow-lg flex items-center justify-center border-2 border-slate-950 hover:bg-emerald-500 hover:scale-110 transition-transform">
        ${count}
      </div>
    </div>
  `;
  return L.divIcon({
    html,
    className: 'prism-listing-marker-cluster',
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function createEndpointIcon(label: string, isStart: boolean) {
  const bgClass = isStart ? 'bg-emerald-500' : 'bg-rose-500';
  const html = `
    <div class="cursor-pointer -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
      <div class="w-6 h-6 rounded-full ${bgClass} text-white font-extrabold text-2xs shadow-lg flex items-center justify-center border-2 border-slate-950">
        ${label}
      </div>
    </div>
  `;

  return L.divIcon({
    html,
    className: 'prism-endpoint-marker',
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

// Subcomponent that manages zoom-aware clustering within MapContainer
function ListingClusterMarkers({
  listings,
  selectedListingId,
  onSelectListing,
}: {
  listings: RouteListingGeo[];
  selectedListingId: string | null;
  onSelectListing: (id: string) => void;
}) {
  const map = useMap();
  const [currentZoom, setCurrentZoom] = useState(() => map.getZoom());

  useEffect(() => {
    const handleMoveOrZoom = () => {
      setCurrentZoom(map.getZoom());
    };
    map.on('zoomend', handleMoveOrZoom);
    map.on('moveend', handleMoveOrZoom);
    return () => {
      map.off('zoomend', handleMoveOrZoom);
      map.off('moveend', handleMoveOrZoom);
    };
  }, [map]);

  const selectedListing = useMemo(() => {
    if (!selectedListingId) return null;
    return listings.find((l) => l.id === selectedListingId && l.lat !== null && l.lon !== null) ?? null;
  }, [listings, selectedListingId]);

  const otherListings = useMemo(() => {
    return listings.filter((l) => l.lat !== null && l.lon !== null && l.id !== selectedListingId);
  }, [listings, selectedListingId]);

  const clusters = useMemo(() => {
    const CLUSTER_DISTANCE_PX = 32;
    type Cluster = {
      key: string;
      centerLat: number;
      centerLon: number;
      items: RouteListingGeo[];
    };
    const list: Cluster[] = [];

    for (const item of otherListings) {
      const pt = map.project([item.lat!, item.lon!], currentZoom);
      let joined = false;
      for (const cluster of list) {
        const clusterPt = map.project([cluster.centerLat, cluster.centerLon], currentZoom);
        if (Math.hypot(pt.x - clusterPt.x, pt.y - clusterPt.y) < CLUSTER_DISTANCE_PX) {
          cluster.items.push(item);
          const n = cluster.items.length;
          cluster.centerLat = (cluster.centerLat * (n - 1) + item.lat!) / n;
          cluster.centerLon = (cluster.centerLon * (n - 1) + item.lon!) / n;
          joined = true;
          break;
        }
      }
      if (!joined) {
        list.push({
          key: `cluster-${item.id}`,
          centerLat: item.lat!,
          centerLon: item.lon!,
          items: [item],
        });
      }
    }
    return list;
  }, [otherListings, currentZoom, map]);

  return (
    <>
      {/* Selected Listing Pill */}
      {selectedListing && selectedListing.lat !== null && selectedListing.lon !== null && (
        <Marker
          key={`selected-${selectedListing.id}`}
          position={[selectedListing.lat, selectedListing.lon]}
          icon={createSelectedPillIcon(selectedListing.detour_min)}
          zIndexOffset={1000}
          eventHandlers={{
            click: () => onSelectListing(selectedListing.id),
          }}
        />
      )}

      {/* Unselected Clusters and Dots */}
      {clusters.map((cluster) => {
        if (cluster.items.length === 1) {
          const item = cluster.items[0];
          return (
            <Marker
              key={`item-${item.id}`}
              position={[item.lat!, item.lon!]}
              icon={createDotIcon(item.detour_min)}
              eventHandlers={{
                click: () => onSelectListing(item.id),
              }}
            />
          );
        }

        return (
          <Marker
            key={cluster.key}
            position={[cluster.centerLat, cluster.centerLon]}
            icon={createClusterIcon(cluster.items.length)}
            zIndexOffset={500}
            eventHandlers={{
              click: () => {
                map.setView(
                  [cluster.centerLat, cluster.centerLon],
                  Math.min(map.getZoom() + 2, 15)
                );
              },
            }}
          />
        );
      })}
    </>
  );
}

export default function RouteCorridorMap({
  polyline,
  circles,
  listings,
  selectedListingId,
  onSelectListing,
  originName,
  destinationName,
  className = '',
}: RouteCorridorMapProps) {
  const { t } = useTranslation();

  // Compute total map bounds
  const bounds = useMemo(() => {
    const latLngs: L.LatLngExpression[] = [];

    polyline.forEach(([lat, lon]) => {
      latLngs.push([lat, lon]);
    });

    circles.forEach((circle) => {
      if (circle.lat !== null && circle.lon !== null) {
        latLngs.push([circle.lat, circle.lon]);
      }
    });

    if (latLngs.length === 0) return null;
    return L.latLngBounds(latLngs);
  }, [polyline, circles]);

  const defaultCenter: [number, number] = polyline.length > 0
    ? polyline[Math.floor(polyline.length / 2)]
    : [48.137, 11.576]; // Default fallback Munich

  const startPoint = polyline.length > 0 ? polyline[0] : null;
  const endPoint = polyline.length > 1 ? polyline[polyline.length - 1] : null;

  return (
    <div className={`w-full h-full min-h-[300px] rounded-2xl overflow-hidden relative border border-border-subtle shadow-2xl bg-bg-base ${className}`}>
      <MapContainer
        center={defaultCenter}
        zoom={9}
        scrollWheelZoom={true}
        className="w-full h-full min-h-[300px] z-10"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <MapBoundsFitter bounds={bounds} />

        {/* Route Polyline */}
        {polyline.length > 1 && (
          <Polyline
            positions={polyline}
            pathOptions={{
              color: '#10b981',
              weight: 5,
              opacity: 0.9,
              lineCap: 'round',
              lineJoin: 'round',
            }}
          />
        )}

        {/* Search Circles */}
        {circles.map((circle, index) => {
          if (circle.lat === null || circle.lon === null) return null;
          return (
            <Circle
              key={`circle-${circle.location_id || index}`}
              center={[circle.lat, circle.lon]}
              radius={circle.radius_km * 1000}
              pathOptions={{
                color: '#10b981',
                fillColor: '#10b981',
                fillOpacity: 0.07,
                weight: 1.5,
                dashArray: '6, 6',
              }}
            >
              <Popup>
                <div className="text-xs font-sans text-slate-200 space-y-1">
                  <div className="font-bold text-emerald-400">
                    {t('routeResults.legendSearchArea')} #{index + 1}
                  </div>
                  <div className="font-semibold">{circle.label}</div>
                  <div className="text-2xs text-slate-400">
                    {t('routeResults.circlePopup', { label: circle.label, radius: circle.radius_km })}
                  </div>
                </div>
              </Popup>
            </Circle>
          );
        })}

        {/* Origin and Destination Pin Markers */}
        {startPoint && (
          <Marker
            position={startPoint}
            icon={createEndpointIcon('A', true)}
          >
            <Popup>
              <div className="text-xs font-sans text-slate-200">
                <span className="font-bold text-emerald-400 block">{t('routeResults.originPin', { place: originName || 'Start' })}</span>
              </div>
            </Popup>
          </Marker>
        )}

        {endPoint && (
          <Marker
            position={endPoint}
            icon={createEndpointIcon('B', false)}
          >
            <Popup>
              <div className="text-xs font-sans text-slate-200">
                <span className="font-bold text-rose-400 block">{t('routeResults.destinationPin', { place: destinationName || 'Destination' })}</span>
              </div>
            </Popup>
          </Marker>
        )}

        {/* Clustered and Dot Listing Markers */}
        <ListingClusterMarkers
          listings={listings}
          selectedListingId={selectedListingId}
          onSelectListing={onSelectListing}
        />
      </MapContainer>

      {/* Map Legend Overlay */}
      <div className="absolute bottom-3 left-3 z-[400] bg-bg-surface/85 backdrop-blur-md border border-border-subtle rounded-xl px-3 py-1.5 flex items-center gap-3 text-2xs font-semibold text-text-secondary pointer-events-none">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-1 bg-emerald-500 rounded-full" />
          <span>{t('routeResults.legendRoute')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full border border-dashed border-emerald-400 bg-emerald-500/10" />
          <span>{t('routeResults.legendSearchArea')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400 ring-1 ring-slate-950" />
          <span>{t('routeResults.legendListing')}</span>
        </div>
      </div>
    </div>
  );
}
