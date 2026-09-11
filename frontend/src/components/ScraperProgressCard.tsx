import { useTranslation } from '../hooks/useTranslation';
import type { ScraperProgressCardProps } from '../types';

export default function ScraperProgressCard({
  isScraping,
  scrapingStatus,
  scrapingProgress,
}: ScraperProgressCardProps) {
  const { t } = useTranslation();

  if (!isScraping) return null;

  const current = scrapingProgress?.current ?? 0;
  const total = scrapingProgress?.total ?? 100;
  const pct = total > 0 ? Math.min(100, Math.max(0, Math.round((current / total) * 100))) : 0;
  const phase = scrapingProgress?.phase || 'starting';
  const remaining = total - current;
  const secondsLeft = Math.max(0, remaining * 3);

  let phaseLabel = "Initializing";
  let phaseColor = "bg-bg-surface text-text-muted border border-border-subtle";
  let barColor = "from-brand-accent/60 to-brand-accent animate-pulse";
  
  if (phase === 'discovery') {
    phaseLabel = "Discovery Phase (Index Page Crawl)";
    phaseColor = "bg-brand-accent/10 text-brand-accent border border-brand-accent/25";
    barColor = "from-brand-accent/80 to-brand-accent";
  } else if (phase === 'harvesting') {
    phaseLabel = "Enrichment Phase (Sequential Page Harvest)";
    phaseColor = "bg-status-good/10 text-status-good border border-status-good/25";
    barColor = "from-status-good to-status-good/80 shadow-[0_0_8px_rgba(16,185,129,0.3)]";
  }

  return (
    <div className="bg-bg-surface/90 backdrop-blur-2xl border border-border-subtle rounded-2xl p-6 shadow-2xl space-y-4 animate-fadeIn my-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <div className="animate-spin w-4 h-4 border-2 border-status-good border-t-transparent rounded-full" />
            <h3 className="text-base font-bold text-text-primary">{t('common.activeScrapingSession')}</h3>
            <span className={`text-sm px-2.5 py-0.5 rounded-full font-medium ${phaseColor}`}>
              {phaseLabel}
            </span>
          </div>
          <p className="text-sm text-text-secondary leading-relaxed font-medium">
            {scrapingStatus || "Connecting to background scraper worker..."}
          </p>
        </div>
        <div className="text-right shrink-0">
          <span className="text-2xl sm:text-3xl font-bold text-status-good font-mono tracking-tight">{pct}%</span>
          <span className="text-sm text-text-muted block font-medium">{t('common.completedOf', { current, total })}</span>
        </div>
      </div>

      {/* Progress Bar Container */}
      <div className="w-full bg-bg-base/80 h-3 rounded-full overflow-hidden p-0.5 border border-border-subtle shadow-inner">
        <div 
          className={`h-full rounded-full bg-gradient-to-r ${barColor} transition-all duration-500 relative`}
          style={{ width: `${pct}%` }}
        >
          {/* Shine animation */}
          <div className="absolute inset-0 bg-white/20 animate-pulse" />
        </div>
      </div>

      {/* Time Remaining & Meta Details */}
      <div className="flex items-center justify-between text-sm text-text-muted font-medium px-1 pt-0.5">
        <div>
          {phase === 'harvesting' && remaining > 0 ? (
            <span className="flex items-center space-x-1">
              <svg className="w-3.5 h-3.5 text-status-good" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              <span>{t('common.estimatedRemaining')}<strong className="text-text-primary font-semibold">{secondsLeft}s</strong></span>
            </span>
          ) : phase === 'harvesting' ? (
            <span className="text-status-good font-semibold">{t('common.finalizingSession')}</span>
          ) : phase === 'discovery' ? (
            <span className="text-brand-accent font-medium">{t('common.discoveringListings')}</span>
          ) : (
            <span className="text-text-secondary">{t('common.connectingWorker')}</span>
          )}
        </div>
        <div className="text-sm text-text-muted font-medium select-none">
          {t('common.liveScraper')}
        </div>
      </div>
    </div>
  );
}
