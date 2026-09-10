/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import RouteCorridorMap from './RouteCorridorMap';
import type { RouteCircle, RouteListingGeo } from './RouteCorridorMap';
import { Button } from './ui/Button';
import { Card } from './ui/Card';
import { Input } from './ui/Input';
import { Select } from './ui/Select';
import { Search, Sparkles, Navigation, Clock, ExternalLink, RefreshCw, Filter } from 'lucide-react';
import ScraperProgressCard from './ScraperProgressCard';
import type { ScraperProgressCardProps } from '../types';

export interface RouteCorridorData {
  route: {
    id: number;
    campaign_id: number;
    name: string;
    origin: string;
    destination: string;
    radius_km: number;
    half_width_km: number;
    distance_km: number | null;
    duration_min: number | null;
    polyline: [number, number][];
    circles: RouteCircle[];
  };
  listings: RouteListingGeo[];
  counts: {
    total: number;
    routed: number;
    unplaced: number;
  };
}

interface RouteResultsViewProps {
  campaignId: number;
  campaignName: string;
  onEvaluateWithAi: () => void;
  isScraping: boolean;
  onStartScrape: () => void;
  scrapingStatus?: string;
  scrapingProgress?: ScraperProgressCardProps['scrapingProgress'] | null;
  liveLogs?: string;
  showLogConsole?: boolean;
  setShowLogConsole?: (val: boolean) => void;
}

export default function RouteResultsView({
  campaignId,
  campaignName,
  onEvaluateWithAi,
  isScraping,
  onStartScrape,
  scrapingStatus = '',
  scrapingProgress = null,
  liveLogs = '',
  showLogConsole = false,
  setShowLogConsole,
}: RouteResultsViewProps) {
  const { t } = useTranslation();

  const [routeData, setRouteData] = useState<RouteCorridorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters and sorting
  const [selectedDetourMax, setSelectedDetourMax] = useState<'all' | '15' | '30' | '60'>('all');
  const [sortBy, setSortBy] = useState<'detour' | 'price' | 'date'>('detour');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null);

  const fetchRouteData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/campaigns/${campaignId}/route`);
      if (!res.ok) {
        if (res.status === 404) {
          setError('no_route');
        } else {
          setError('fetch_failed');
        }
        setRouteData(null);
        return;
      }
      const data: RouteCorridorData = await res.json();
      setRouteData(data);
    } catch {
      setError('network_error');
    } finally {
      setLoading(false);
    }
  }, [campaignId]);

  useEffect(() => {
    fetchRouteData();
  }, [fetchRouteData]);

  // Refresh when scraping finishes
  useEffect(() => {
    if (!isScraping) {
      fetchRouteData();
    }
  }, [isScraping, fetchRouteData]);

  // Parse price string e.g. "70 €", "VB", "Zu verschenken" to a sortable number
  const parsePrice = (priceStr: string): number => {
    if (!priceStr) return 999999;
    const match = priceStr.replace(/\./g, '').replace(/,/g, '.').match(/\d+(\.\d+)?/);
    return match ? parseFloat(match[0]) : 999999;
  };

  // Filtered and sorted listings
  const filteredListings = useMemo(() => {
    if (!routeData) return [];
    let list = [...routeData.listings];

    // Detour filter
    if (selectedDetourMax !== 'all') {
      const maxMin = parseInt(selectedDetourMax, 10);
      list = list.filter((l) => l.detour_min !== null && l.detour_min <= maxMin);
    }

    // Text search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (l) => l.title.toLowerCase().includes(q) || l.location.toLowerCase().includes(q)
      );
    }

    // Sort
    list.sort((a, b) => {
      if (sortBy === 'detour') {
        if (a.detour_min === null && b.detour_min === null) return 0;
        if (a.detour_min === null) return 1;
        if (b.detour_min === null) return -1;
        return a.detour_min - b.detour_min;
      }
      if (sortBy === 'price') {
        return parsePrice(a.price) - parsePrice(b.price);
      }
      return 0; // default database order
    });

    return list;
  }, [routeData, selectedDetourMax, searchQuery, sortBy]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-400 space-y-3">
        <div className="animate-spin w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full" />
        <p className="text-xs font-semibold">{t('common.loading')}</p>
      </div>
    );
  }

  if (error || !routeData) {
    return (
      <Card className="p-8 text-center space-y-4 max-w-xl mx-auto my-8">
        <p className="text-slate-300 font-bold text-sm">
          {error === 'no_route' ? t('dashboard.noSearches') : t('common.connectionIssueFailed')}
        </p>
        <Button variant="primary" size="sm" onClick={fetchRouteData}>
          {t('common.cancel')}
        </Button>
      </Card>
    );
  }

  const { route, counts } = routeData;
  const hasListings = counts.total > 0;

  return (
    <div className="flex flex-col space-y-5 animate-fadeIn w-full">
      {/* Top Corridor Overview Card */}
      <Card className="p-5 relative overflow-hidden bg-slate-950/80 border-slate-800">
        <div className="absolute -right-20 -top-20 w-48 h-48 rounded-full bg-emerald-500/10 blur-3xl pointer-events-none" />

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-2xs font-mono font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full uppercase tracking-wider">
                {t('routeResults.corridorResults')}
              </span>
              {route.distance_km && route.duration_min && (
                <span className="text-2xs text-slate-400 font-semibold flex items-center gap-1">
                  <Navigation className="w-3 h-3 text-emerald-400" />
                  {t('routeResults.routeStats', {
                    distance: route.distance_km,
                    duration: route.duration_min,
                  })}
                </span>
              )}
              <span className="text-2xs text-slate-500">·</span>
              <span className="text-2xs text-slate-400 font-semibold">
                {t('routeResults.searchCirclesCount', { count: route.circles.length })}
              </span>
            </div>

            {/* Headline Fact */}
            <h1 className="text-xl font-extrabold text-slate-100 tracking-tight font-sans">
              {hasListings ? (
                counts.total === 1 ? (
                  t('routeResults.listingsFoundSingular')
                ) : (
                  t('routeResults.listingsFound', { count: counts.total })
                )
              ) : (
                t('routeResults.noListingsFound')
              )}
            </h1>

            <p className="text-xs text-slate-400">
              <span className="font-semibold text-slate-200">{campaignName}</span>: {route.origin} → {route.destination}
            </p>
          </div>

          {/* Action CTAs */}
          <div className="flex flex-wrap items-center gap-3 shrink-0">
            <Button
              id="btn-corridor-scrape"
              variant="action-emerald"
              size="sm"
              onClick={onStartScrape}
              disabled={isScraping}
              className="py-2.5 px-4 font-bold flex items-center gap-2"
            >
              {isScraping ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>{t('routeResults.scrapingInProgress')}</span>
                </>
              ) : (
                <>
                  <Search className="w-4 h-4" />
                  <span>{t('routeResults.startScrape')}</span>
                </>
              )}
            </Button>

            <Button
              id="btn-evaluate-ai"
              variant="action-indigo"
              size="sm"
              onClick={onEvaluateWithAi}
              className="py-2.5 px-4 font-bold flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              <span>{t('routeResults.evaluateWithAi')}</span>
            </Button>
          </div>
        </div>
      </Card>

      {/* Scraper Progress Tracker (if active) */}
      <ScraperProgressCard
        isScraping={isScraping}
        scrapingStatus={scrapingStatus}
        scrapingProgress={scrapingProgress}
        liveLogs={liveLogs || ''}
        showLogConsole={showLogConsole}
        setShowLogConsole={setShowLogConsole || (() => {})}
      />

      {/* Main Content Area */}
      {!hasListings ? (
        /* Empty State: Invitation to Act */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          <div className="lg:col-span-7 h-[420px] rounded-2xl overflow-hidden">
            <RouteCorridorMap
              polyline={route.polyline}
              circles={route.circles}
              listings={[]}
              selectedListingId={null}
              onSelectListing={() => {}}
              originName={route.origin}
              destinationName={route.destination}
            />
          </div>

          <div className="lg:col-span-5">
            <Card className="p-8 text-center space-y-4 border-emerald-500/20 bg-slate-950/70">
              <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto text-emerald-400">
                <Navigation className="w-6 h-6" />
              </div>

              <div className="space-y-1.5">
                <h3 className="text-base font-extrabold text-slate-100">
                  {t('routeResults.emptyHeadline')}
                </h3>
                <p className="text-xs text-slate-400 leading-relaxed font-semibold">
                  {t('routeResults.emptyExplanation', { count: route.circles.length })}
                </p>
              </div>

              <div className="pt-3">
                <Button
                  id="btn-empty-scrape"
                  variant="primary"
                  size="md"
                  onClick={onStartScrape}
                  disabled={isScraping}
                  className="w-full py-3 text-base font-bold shadow-lg shadow-emerald-950/50"
                >
                  {isScraping ? t('routeResults.scrapingInProgress') : t('routeResults.emptyAction')}
                </Button>
              </div>
            </Card>
          </div>
        </div>
      ) : (
        /* Populated Results View */
        <div className="space-y-4">
          {/* Filter & Sorting Controls */}
          <Card className="p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-950/60 border-border-subtle">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-2xs text-slate-500 font-bold uppercase tracking-wider flex items-center gap-1 mr-1">
                <Filter className="w-3 h-3 text-slate-400" />
                {t('routeResults.detourFilterLabel')}:
              </span>

              {(['all', '15', '30', '60'] as const).map((choice) => {
                const label =
                  choice === 'all'
                    ? t('routeResults.allDetours')
                    : choice === '15'
                    ? t('routeResults.within15Min')
                    : choice === '30'
                    ? t('routeResults.within30Min')
                    : t('routeResults.within60Min');

                const active = selectedDetourMax === choice;
                return (
                  <button
                    key={choice}
                    type="button"
                    onClick={() => setSelectedDetourMax(choice)}
                    className={`px-2.5 py-1 rounded-lg text-2xs font-semibold transition-colors ${
                      active
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-2">
              <div className="relative w-full sm:w-56">
                <Input
                  type="text"
                  placeholder={t('routeResults.searchPlaceholder')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="text-xs py-1.5"
                />
              </div>

              <div className="w-full sm:w-44">
                <Select
                  value={sortBy}
                  onChange={(val) => setSortBy(val as 'detour' | 'price' | 'date')}
                  options={[
                    { value: 'detour', label: t('routeResults.sortByDetour') },
                    { value: 'price', label: t('routeResults.sortByPrice') },
                    { value: 'date', label: t('routeResults.sortByDate') },
                  ]}
                  className="text-xs py-1.5"
                />
              </div>
            </div>
          </Card>

          {/* Interactive Split Layout: Map & Listings List */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Map Column (Desktop Sticky) */}
            <div className="lg:col-span-6 xl:col-span-7 h-[360px] lg:h-[calc(100vh-250px)] lg:sticky lg:top-20 z-10">
              <RouteCorridorMap
                polyline={route.polyline}
                circles={route.circles}
                listings={filteredListings}
                selectedListingId={selectedListingId}
                onSelectListing={setSelectedListingId}
                originName={route.origin}
                destinationName={route.destination}
              />
            </div>

            {/* Listings Column */}
            <div className="lg:col-span-6 xl:col-span-5 space-y-3 max-h-[calc(100vh-250px)] lg:overflow-y-auto lg:pr-1 scrollbar-thin">
              {filteredListings.length === 0 ? (
                <div className="bg-slate-900/40 border border-dashed border-slate-800 rounded-2xl p-10 text-center space-y-2">
                  <p className="text-xs font-semibold text-slate-400">
                    {t('routeResults.noFilterMatches')}
                  </p>
                  <Button
                    variant="badge"
                    size="xs"
                    onClick={() => {
                      setSelectedDetourMax('all');
                      setSearchQuery('');
                    }}
                  >
                    {t('routeResults.resetFilters')}
                  </Button>
                </div>
              ) : (
                filteredListings.map((l) => {
                  const isSelected = selectedListingId === l.id;
                  const firstImg = l.images && l.images.length > 0 ? l.images[0] : null;

                  return (
                    <div
                      key={l.id}
                      onClick={() => setSelectedListingId(l.id)}
                      className={`group p-3.5 rounded-2xl border transition-all cursor-pointer bg-slate-950/70 hover:bg-slate-900/80 ${
                        isSelected
                          ? 'border-emerald-400/60 ring-2 ring-emerald-500/20 shadow-lg shadow-emerald-950/30'
                          : 'border-slate-800/80 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex gap-3">
                        {/* Thumbnail */}
                        {firstImg ? (
                          <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-xl overflow-hidden shrink-0 border border-slate-800 bg-slate-900">
                            <img
                              src={firstImg}
                              alt={l.title}
                              className="w-full h-full object-cover transition-transform group-hover:scale-105"
                            />
                          </div>
                        ) : (
                          <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-xl shrink-0 border border-slate-800 bg-slate-900/60 flex items-center justify-center text-slate-600 font-mono text-2xs">
                            No image
                          </div>
                        )}

                        {/* Details */}
                        <div className="flex-1 min-w-0 flex flex-col justify-between">
                          <div className="space-y-1">
                            {/* Prominent Detour Badge & Price Row */}
                            <div className="flex items-center justify-between gap-2">
                              {l.detour_min !== null ? (
                                <span className="inline-flex items-center gap-1 text-2xs font-mono font-extrabold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                                  <Clock className="w-3 h-3 text-emerald-400" />
                                  {l.detour_min < 1
                                    ? t('routeResults.onRoute')
                                    : t('routeResults.detourBadge', { minutes: Math.round(l.detour_min) })}
                                </span>
                              ) : (
                                <span className="text-2xs text-slate-500 font-mono">
                                  {t('routeResults.unplacedCount', { count: 1 })}
                                </span>
                              )}

                              <span className="font-mono font-extrabold text-emerald-400 text-sm">
                                {l.price}
                              </span>
                            </div>

                            {/* Title */}
                            <h3 className="text-xs font-bold text-slate-200 line-clamp-2 leading-snug group-hover:text-emerald-300 transition-colors">
                              {l.title}
                            </h3>
                          </div>

                          {/* Location & AI Score & External Link */}
                          <div className="pt-2 flex items-center justify-between gap-2 text-2xs text-slate-400">
                            <div className="flex items-center gap-2 truncate">
                              <span className="truncate">{l.location}</span>
                              {l.offroute_km !== null && (
                                <span className="font-mono text-slate-500 text-2xs shrink-0">
                                  ({l.offroute_km.toFixed(1)} km)
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              {l.llm_processed && l.niceness_score !== null ? (
                                <span className="font-mono font-bold text-indigo-300 bg-indigo-500/15 border border-indigo-500/25 px-1.5 py-0.5 rounded">
                                  {t('routeResults.aiScore', { score: l.niceness_score })}
                                </span>
                              ) : null}

                              <a
                                href={l.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                onClick={(e) => e.stopPropagation()}
                                className="text-slate-400 hover:text-emerald-400 transition-colors p-1"
                                title={t('routeResults.viewOnPlatform')}
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </a>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
