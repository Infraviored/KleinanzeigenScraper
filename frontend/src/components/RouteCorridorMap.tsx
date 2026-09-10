import { useEffect, useMemo } from 'react';
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

// Helper to create custom HTML DivIcons
function createListingIcon(detourMin: number | null, isSelected: boolean) {
  const detourText =
    detourMin !== null
      ? detourMin < 1
        ? '0m'
        : `+${Math.round(detourMin)}m`
      : '•';

  const baseClasses = isSelected
    ? 'bg-emerald-400 text-slate-950 ring-4 ring-emerald-400/40 shadow-emerald-500/50 scale-110 z-30 font-extrabold'
    : 'bg-slate-950/90 text-emerald-300 border border-emerald-500/40 hover:border-emerald-400 hover:scale-105 shadow-black/80 z-20 font-bold';

  const html = `
    <div class="cursor-pointer transition-transform duration-200 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
      <div class="px-2 py-0.5 rounded-full text-2xs font-mono shadow-lg flex items-center gap-1 whitespace-nowrap ${baseClasses}">
        <span class="w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-slate-950' : 'bg-emerald-400'}"></span>
        <span>${detourText}</span>
      </div>
    </div>
  `;

  return L.divIcon({
    html,
    className: 'prism-listing-marker',
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

export default function RouteCorridorMap({
  polyline,
  circles,
  listings,
  selectedListingId,
  onSelectListing,
  originName,
  destinationName,
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

    listings.forEach((listing) => {
      if (listing.lat !== null && listing.lon !== null) {
        latLngs.push([listing.lat, listing.lon]);
      }
    });

    if (latLngs.length === 0) return null;
    return L.latLngBounds(latLngs);
  }, [polyline, circles, listings]);

  const defaultCenter: [number, number] = polyline.length > 0
    ? polyline[Math.floor(polyline.length / 2)]
    : [48.137, 11.576]; // Default fallback Munich

  const startPoint = polyline.length > 0 ? polyline[0] : null;
  const endPoint = polyline.length > 1 ? polyline[polyline.length - 1] : null;

  return (
    <div className="w-full h-full min-h-[360px] lg:min-h-[440px] rounded-2xl overflow-hidden relative border border-slate-800/80 shadow-2xl bg-slate-950">
      <MapContainer
        center={defaultCenter}
        zoom={9}
        scrollWheelZoom={true}
        className="w-full h-full min-h-[360px] lg:min-h-[440px] z-10"
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
              color: '#059669',
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

        {/* Listing Pins */}
        {listings.map((l) => {
          if (l.lat === null || l.lon === null) return null;
          const isSelected = selectedListingId === l.id;
          const firstImg = l.images && l.images.length > 0 ? l.images[0] : null;

          return (
            <Marker
              key={`listing-${l.id}`}
              position={[l.lat, l.lon]}
              icon={createListingIcon(l.detour_min, isSelected)}
              eventHandlers={{
                click: () => onSelectListing(l.id),
              }}
            >
              <Popup>
                <div className="text-xs font-sans text-slate-200 space-y-2 max-w-[240px]">
                  {firstImg && (
                    <div className="w-full aspect-[16/9] rounded-lg overflow-hidden border border-slate-700 bg-slate-900">
                      <img src={firstImg} alt={l.title} className="w-full h-full object-cover" />
                    </div>
                  )}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono font-bold text-emerald-400 text-sm">{l.price}</span>
                      {l.detour_min !== null && (
                        <span className="text-2xs font-mono font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/25 px-1.5 py-0.5 rounded">
                          {l.detour_min < 1 ? t('routeResults.onRoute') : t('routeResults.detourBadge', { minutes: Math.round(l.detour_min) })}
                        </span>
                      )}
                    </div>
                    <h4 className="font-bold text-slate-100 line-clamp-2 leading-snug">{l.title}</h4>
                    <p className="text-2xs text-slate-400">{l.location}</p>
                    {l.offroute_km !== null && (
                      <p className="text-2xs text-slate-400 font-mono">
                        {t('routeResults.offRouteDistance', { km: l.offroute_km.toFixed(1) })}
                      </p>
                    )}
                  </div>
                  <div className="pt-1 border-t border-slate-800 flex justify-between items-center">
                    <a
                      href={l.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-2xs text-emerald-400 hover:text-emerald-300 font-bold hover:underline"
                    >
                      {t('routeResults.viewOnPlatform')} ↗
                    </a>
                  </div>
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Map Legend Overlay */}
      <div className="absolute bottom-3 left-3 z-[400] bg-slate-950/85 backdrop-blur-md border border-slate-800 rounded-xl px-3 py-1.5 flex items-center gap-3 text-2xs font-semibold text-slate-300 pointer-events-none">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-1 bg-emerald-500 rounded-full" />
          <span>{t('routeResults.legendRoute')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full border border-dashed border-emerald-400 bg-emerald-500/10" />
          <span>{t('routeResults.legendSearchArea')}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <span>{t('routeResults.legendListing')}</span>
        </div>
      </div>
    </div>
  );
}
