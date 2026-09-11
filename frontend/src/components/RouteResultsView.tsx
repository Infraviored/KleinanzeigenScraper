/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import RouteCorridorMap from './RouteCorridorMap';
import type { RouteCircle, RouteListingGeo } from './RouteCorridorMap';
import { Button } from './ui/Button';
import { Card } from './ui/Card';
import { Input } from './ui/Input';
import { Select } from './ui/Select';
import {
  Search,
  Sparkles,
  Navigation,
  RefreshCw,
  Filter,
  SlidersHorizontal,
  ListFilter,
  MapPin,
  X,
} from 'lucide-react';
import ScraperProgressCard from './ScraperProgressCard';
import CorridorPlanner from './CorridorPlanner';
import type { ScraperProgressCardProps } from '../types';

export interface RouteCorridorData {
  route: {
    id: number;
    campaign_id: number;
    name: string;
    base_url: string;
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
  const [draft, setDraft] = useState<{ radius: number; corridor: number } | null>(null);
  const [redrawing, setRedrawing] = useState(false);
  const [redrawError, setRedrawError] = useState<string | null>(null);
  const [selectedDetourMax, setSelectedDetourMax] = useState<'all' | '15' | '30' | '60'>('all');
  const [sortBy, setSortBy] = useState<'detour' | 'price'>('detour');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedListingId, setSelectedListingId] = useState<string | null>(null);

  // Responsive switch for screens below lg (1024px)
  const [mobileTab, setMobileTab] = useState<'list' | 'map'>('list');
  const [isDesktop, setIsDesktop] = useState(
    typeof window !== 'undefined' ? window.innerWidth >= 1024 : false
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mql = window.matchMedia('(min-width: 1024px)');
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    setIsDesktop(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  // Lock body scroll when mobile corridor settings drawer is open
  useEffect(() => {
    if (draft && !isDesktop) {
      const prevOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = prevOverflow;
      };
    }
  }, [draft, isDesktop]);

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
    if (!isScraping) {
      fetchRouteData();
    }
  }, [isScraping, fetchRouteData]);

  const redrawCorridor = useCallback(async () => {
    if (!draft || !routeData) return;
    setRedrawing(true);
    setRedrawError(null);
    try {
      const res = await fetch(`/api/route-searches/${routeData.route.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          radius_km: draft.radius,
          corridor_km: draft.corridor,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setRedrawError(data.error || t('common.connectionIssueFailed'));
        return;
      }
      setRouteData(data);
      setDraft(null);
    } catch {
      setRedrawError(t('common.connectionIssueFailed'));
    } finally {
      setRedrawing(false);
    }
  }, [draft, routeData, t]);

  const parsePrice = (priceStr: string): number => {
    if (!priceStr) return 999999;
    const match = priceStr.replace(/\./g, '').replace(/,/g, '.').match(/\d+(\.\d+)?/);
    return match ? parseFloat(match[0]) : 999999;
  };

  const filteredListings = useMemo(() => {
    if (!routeData) return [];
    let list = [...routeData.listings];

    if (selectedDetourMax !== 'all') {
      const maxMin = parseInt(selectedDetourMax, 10);
      list = list.filter((l) => l.detour_min !== null && l.detour_min <= maxMin);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (l) => l.title.toLowerCase().includes(q) || l.location.toLowerCase().includes(q)
      );
    }

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
      return 0;
    });

    return list;
  }, [routeData, selectedDetourMax, searchQuery, sortBy]);

  const selectedListing = useMemo(() => {
    if (!selectedListingId) return null;
    return filteredListings.find((l) => l.id === selectedListingId) ?? null;
  }, [filteredListings, selectedListingId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-text-muted space-y-3">
        <div className="animate-spin w-8 h-8 border-2 border-brand-accent border-t-transparent rounded-full" />
        <p className="text-xs font-semibold">{t('common.loading')}</p>
      </div>
    );
  }

  if (error || !routeData) {
    return (
      <Card className="p-8 text-center space-y-4 max-w-xl mx-auto my-8 bg-bg-surface border-border-subtle">
        <p className="text-text-primary font-bold text-sm">
          {error === 'no_route' ? t('dashboard.noSearches') : t('common.connectionIssueFailed')}
        </p>
        <Button variant="primary" size="sm" onClick={fetchRouteData}>
          {t('common.retry')}
        </Button>
      </Card>
    );
  }

  const { route, counts } = routeData;
  const hasListings = counts.total > 0;

  return (
    <div className="flex flex-col space-y-4 animate-fadeIn w-full">
      {/* Top Corridor Overview Card */}
      <Card className="p-4 sm:p-5 relative overflow-hidden bg-bg-surface border-border-subtle">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-2xs font-mono font-bold bg-brand-accent/15 text-brand-accent border border-brand-accent/30 px-2 py-0.5 rounded-full uppercase tracking-wider">
                {t('routeResults.corridorResults')}
              </span>
              {route.distance_km && route.duration_min && (
                <span className="text-2xs text-text-muted font-semibold flex items-center gap-1">
                  <Navigation className="w-3 h-3 text-brand-accent" />
                  {t('routeResults.routeStats', {
                    distance: route.distance_km,
                    duration: route.duration_min,
                  })}
                </span>
              )}
              <span className="text-2xs text-text-muted font-semibold">
                {t('routeResults.searchCirclesCount', { count: route.circles.length })}
              </span>
            </div>

            {/* Headline Fact */}
            <h1 className="text-lg sm:text-xl font-extrabold text-text-primary tracking-tight font-heading">
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

            <p className="text-xs text-text-muted">
              <span className="font-semibold text-text-secondary">{campaignName}</span>: {route.origin} → {route.destination}
            </p>
          </div>

          {/* Action CTAs */}
          <div className="grid grid-cols-2 sm:flex sm:flex-wrap items-center gap-2 sm:gap-3 shrink-0">
            <Button
              id="btn-corridor-scrape"
              variant="action-emerald"
              size="sm"
              onClick={onStartScrape}
              disabled={isScraping}
              className="py-2.5 px-3 font-bold flex items-center justify-center gap-2 min-h-[44px]"
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
              variant="secondary"
              size="sm"
              onClick={() =>
                setDraft({
                  radius: routeData.route.radius_km,
                  corridor: routeData.route.half_width_km,
                })
              }
              className="py-2.5 px-3 font-bold flex items-center justify-center gap-2 min-h-[44px]"
            >
              <SlidersHorizontal className="w-4 h-4" />
              <span>{t('corridor.editSettings')}</span>
            </Button>

            <Button
              id="btn-evaluate-ai"
              variant="action-indigo"
              size="sm"
              onClick={onEvaluateWithAi}
              className="col-span-2 sm:col-span-1 py-2.5 px-3 font-bold flex items-center justify-center gap-2 min-h-[44px]"
            >
              <Sparkles className="w-4 h-4" />
              <span>{t('routeResults.evaluateWithAi')}</span>
            </Button>
          </div>
        </div>
      </Card>

      {/* Corridor Settings Drawer / Overlay */}
      {draft && (
        <div
          className="fixed inset-0 z-50 overflow-y-auto bg-bg-base/95 backdrop-blur-md p-4 lg:static lg:bg-transparent lg:overflow-visible lg:p-0 lg:z-auto animate-fadeIn"
          role="dialog"
          aria-modal="true"
          aria-label={t('corridor.editSettings')}
        >
          <Card className="p-4 sm:p-5 space-y-4 max-w-4xl mx-auto bg-bg-surface border-border-subtle shadow-2xl">
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-1">
                <h3 className="text-lg font-bold text-text-primary">{t('corridor.editSettings')}</h3>
                <p className="text-sm text-text-muted">{t('corridor.widthHint')}</p>
              </div>
              <button
                type="button"
                onClick={() => { setDraft(null); setRedrawError(null); }}
                className="lg:hidden p-2 min-w-[44px] min-h-[44px] flex items-center justify-center text-text-muted hover:text-text-primary rounded-xl"
                aria-label={t('corridor.closeSettings')}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <CorridorPlanner
              baseUrl={route.base_url}
              origin={route.origin}
              destination={route.destination}
              originName={route.origin}
              destinationName={route.destination}
              radiusKm={draft.radius}
              corridorKm={draft.corridor}
              onRadiusChange={radius => setDraft(d => (d ? { ...d, radius } : d))}
              onCorridorChange={corridor => setDraft(d => (d ? { ...d, corridor } : d))}
              committing={redrawing}
              commitLabel={t('corridor.commitChange')}
              onCancel={() => { setDraft(null); setRedrawError(null); }}
              onCommit={redrawCorridor}
            />
            {redrawError && (
              <p className="text-sm text-brand-accent font-semibold">{redrawError}</p>
            )}
          </Card>
        </div>
      )}

      {/* Scraper Progress Tracker (if active) */}
      <ScraperProgressCard
        isScraping={isScraping}
        scrapingStatus={scrapingStatus}
        scrapingProgress={scrapingProgress}
        liveLogs={liveLogs || ''}
        showLogConsole={showLogConsole}
        setShowLogConsole={setShowLogConsole || (() => {})}
      />

      {/* Mobile Segmented Switch (below lg) */}
      <div className="lg:hidden flex p-1 rounded-xl bg-bg-input border border-border-subtle">
        <button
          type="button"
          onClick={() => setMobileTab('list')}
          className={`flex-1 min-h-[44px] py-2 px-4 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2 ${
            mobileTab === 'list'
              ? 'bg-bg-surface text-text-primary shadow-md border border-border-subtle'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          <ListFilter className="w-4 h-4" />
          <span>{t('routeResults.tabListings', { count: filteredListings.length })}</span>
        </button>
        <button
          type="button"
          onClick={() => setMobileTab('map')}
          className={`flex-1 min-h-[44px] py-2 px-4 rounded-lg text-sm font-bold transition-all flex items-center justify-center gap-2 ${
            mobileTab === 'map'
              ? 'bg-bg-surface text-text-primary shadow-md border border-border-subtle'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          <MapPin className="w-4 h-4" />
          <span>{t('routeResults.tabMap')}</span>
        </button>
      </div>

      {/* Main Content Area */}
      {!hasListings ? (
        /* Empty State */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
          {(isDesktop || mobileTab === 'map') && (
            <div className={`rounded-2xl overflow-hidden ${isDesktop ? 'lg:col-span-7 h-[420px]' : 'h-[360px]'}`}>
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
          )}

          {(isDesktop || mobileTab === 'list') && (
            <div className={isDesktop ? 'lg:col-span-5' : 'w-full'}>
              <Card className="p-8 text-center space-y-4 border-border-subtle bg-bg-surface">
                <div className="w-12 h-12 rounded-2xl bg-brand-accent/10 border border-brand-accent/20 flex items-center justify-center mx-auto text-brand-accent">
                  <Navigation className="w-6 h-6" />
                </div>

                <div className="space-y-1.5">
                  <h3 className="text-base font-extrabold text-text-primary">
                    {t('routeResults.emptyHeadline')}
                  </h3>
                  <p className="text-xs text-text-muted leading-relaxed font-semibold">
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
                    className="w-full py-3 text-base font-bold"
                  >
                    {isScraping ? t('routeResults.scrapingInProgress') : t('routeResults.emptyAction')}
                  </Button>
                </div>
              </Card>
            </div>
          )}
        </div>
      ) : (
        /* Populated Results View */
        <div className="space-y-4">
          {/* Filter & Sorting Controls: on desktop, or on mobile when in list tab */}
          {(isDesktop || mobileTab === 'list') && (
            <Card className="p-3 sm:p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-bg-surface border-border-subtle">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-2xs text-text-muted font-bold uppercase tracking-wider flex items-center gap-1 mr-1">
                  <Filter className="w-3 h-3 text-text-muted" />
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
                      className={`min-h-[36px] px-3 py-1 rounded-lg text-2xs font-semibold transition-colors flex items-center justify-center ${
                        active
                          ? 'bg-brand-accent/20 text-brand-accent border border-brand-accent/40 font-bold'
                          : 'bg-bg-input text-text-muted hover:text-text-secondary border border-border-subtle'
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
                    className="text-xs py-1.5 bg-bg-input border-border-subtle"
                  />
                </div>

                <div className="w-full sm:w-44">
                  <Select
                    value={sortBy}
                    onChange={(val) => setSortBy(val as 'detour' | 'price')}
                    options={[
                      { value: 'detour', label: t('routeResults.sortByDetour') },
                      { value: 'price', label: t('routeResults.sortByPrice') },
                    ]}
                    className="text-xs py-1.5 bg-bg-input border-border-subtle"
                  />
                </div>
              </div>
            </Card>
          )}

          {/* Interactive Split Layout: Map & Listings List */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
            {/* Map Column: Mounted on desktop OR when mobileTab === 'map' */}
            {(isDesktop || mobileTab === 'map') && (
              <div
                className={`w-full relative ${
                  isDesktop
                    ? 'lg:col-span-6 xl:col-span-7 h-[calc(100vh-250px)] lg:sticky lg:top-20 z-10'
                    : 'h-[calc(100vh-280px)] min-h-[460px]'
                }`}
              >
                <RouteCorridorMap
                  polyline={route.polyline}
                  circles={route.circles}
                  listings={filteredListings}
                  selectedListingId={selectedListingId}
                  onSelectListing={setSelectedListingId}
                  originName={route.origin}
                  destinationName={route.destination}
                />

                {/* Floating Card for Selected Listing on Mobile Map View */}
                {!isDesktop && selectedListing && (
                  <div className="absolute bottom-4 left-3 right-3 z-[500] animate-fadeIn">
                    <div className="bg-bg-surface/95 backdrop-blur-md p-3 rounded-2xl border border-border-brand shadow-2xl flex items-center gap-3">
                      {selectedListing.images && selectedListing.images.length > 0 ? (
                        <img
                          src={selectedListing.images[0]}
                          alt={selectedListing.title}
                          className="w-14 h-14 rounded-xl object-cover shrink-0 border border-border-subtle bg-bg-input"
                        />
                      ) : (
                        <div className="w-14 h-14 rounded-xl shrink-0 border border-border-subtle bg-bg-input flex items-center justify-center text-text-muted text-2xs">
                          {t('common.noImage')}
                        </div>
                      )}

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-extrabold text-brand-accent font-mono">
                            {selectedListing.detour_min !== null
                              ? selectedListing.detour_min < 1
                                ? t('routeResults.onRouteShort')
                                : `+${Math.round(selectedListing.detour_min)}m`
                              : ''}
                          </span>
                          <span className="text-xs font-semibold text-text-secondary font-mono">
                            {selectedListing.price}
                          </span>
                        </div>
                        <h4 className="text-xs font-bold text-text-primary truncate mt-0.5">
                          {selectedListing.title}
                        </h4>
                        <p className="text-2xs text-text-muted truncate">
                          {selectedListing.location}
                          {selectedListing.offroute_km !== null ? ` · ${selectedListing.offroute_km.toFixed(1)} km` : ''}
                        </p>
                      </div>

                      <div className="flex flex-col items-end gap-1.5 shrink-0">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedListingId(null);
                          }}
                          className="p-1 text-text-muted hover:text-text-primary rounded-lg"
                          aria-label={t('routeResults.closeCard')}
                        >
                          <X className="w-4 h-4" />
                        </button>
                        <a
                          href={selectedListing.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-2.5 py-1 text-2xs font-bold rounded-lg bg-brand-accent text-white shadow hover:opacity-90 transition-opacity whitespace-nowrap"
                        >
                          {t('routeResults.viewOnPlatform')} ↗
                        </a>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Listings Column: Mounted on desktop OR when mobileTab === 'list' */}
            {(isDesktop || mobileTab === 'list') && (
              <div className="lg:col-span-6 xl:col-span-5 space-y-2.5 max-h-[calc(100vh-250px)] lg:overflow-y-auto lg:pr-1 scrollbar-thin">
                {filteredListings.length === 0 ? (
                  <div className="bg-bg-surface border border-dashed border-border-subtle rounded-2xl p-10 text-center space-y-2">
                    <p className="text-xs font-semibold text-text-muted">
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
                      <a
                        key={l.id}
                        href={l.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() => setSelectedListingId(l.id)}
                        className={`group min-h-[76px] p-2.5 sm:p-3 rounded-2xl border transition-all flex items-center gap-3 cursor-pointer no-underline ${
                          isSelected
                            ? 'bg-bg-surface-hover border-border-brand ring-1 ring-border-brand shadow-lg'
                            : 'bg-bg-surface border-border-subtle hover:bg-bg-surface-hover hover:border-border-brand'
                        }`}
                      >
                        {/* 64px Thumbnail */}
                        {firstImg ? (
                          <div className="w-16 h-16 rounded-xl overflow-hidden shrink-0 border border-border-subtle bg-bg-input">
                            <img
                              src={firstImg}
                              alt={l.title}
                              className="w-full h-full object-cover transition-transform group-hover:scale-105"
                              loading="lazy"
                            />
                          </div>
                        ) : (
                          <div className="w-16 h-16 rounded-xl shrink-0 border border-border-subtle bg-bg-input flex items-center justify-center text-text-muted font-mono text-2xs">
                            {t('common.noImage')}
                          </div>
                        )}

                        {/* Details: Title & Location */}
                        <div className="flex-1 min-w-0 flex flex-col justify-center py-0.5">
                          <h3 className="text-sm font-semibold text-text-primary truncate group-hover:text-brand-accent transition-colors leading-snug">
                            {l.title}
                          </h3>

                          <div className="flex items-center gap-1.5 text-2xs text-text-muted truncate mt-1">
                            <span className="truncate">{l.location}</span>
                            {l.offroute_km !== null && (
                              <span className="font-mono text-text-muted shrink-0">
                                · {l.offroute_km.toFixed(1)} km
                              </span>
                            )}
                            {l.llm_processed && l.niceness_score !== null && (
                              <span className="font-mono font-bold text-text-secondary bg-bg-input border border-border-subtle px-1.5 py-0.5 rounded text-2xs shrink-0 ml-1">
                                ★ {l.niceness_score}
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Cost Column: Detour above Price */}
                        <div className="shrink-0 flex flex-col items-end justify-center text-right pl-2 min-w-[72px]">
                          {l.detour_min !== null ? (
                            l.detour_min < 1 ? (
                              <span className="text-sm font-bold text-brand-accent font-mono leading-none">
                                {t('routeResults.onRouteShort')}
                              </span>
                            ) : (
                              <span className="text-lg font-extrabold text-brand-accent font-mono tracking-tight leading-none">
                                +{Math.round(l.detour_min)}m
                              </span>
                            )
                          ) : (
                            <span className="text-2xs text-text-muted font-mono leading-none">
                              {l.geo_status === 'too_far'
                                ? t('routeResults.offCorridor')
                                : l.geo_status === 'failed'
                                  ? t('routeResults.detourUnknown')
                                  : t('routeResults.noCoordinates')}
                            </span>
                          )}

                          <span className="text-sm font-semibold text-text-secondary font-mono mt-1.5 leading-none">
                            {l.price}
                          </span>
                        </div>
                      </a>
                    );
                  })
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
