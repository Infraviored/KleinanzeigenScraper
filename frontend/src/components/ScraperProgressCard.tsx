import type { ScraperProgressCardProps } from '../types';

export default function ScraperProgressCard({
  isScraping,
  scrapingStatus,
  scrapingProgress,
}: ScraperProgressCardProps) {
  if (!isScraping) return null;

  const current = scrapingProgress?.current ?? 0;
  const total = scrapingProgress?.total ?? 100;
  const pct = total > 0 ? Math.min(100, Math.max(0, Math.round((current / total) * 100))) : 0;
  const phase = scrapingProgress?.phase || 'starting';
  const remaining = total - current;
  const secondsLeft = Math.max(0, remaining * 3);

  let phaseLabel = "Initializing";
  let phaseColor = "bg-amber-500/10 text-amber-400 border border-amber-500/25";
  let barColor = "from-amber-500 to-amber-400 animate-pulse";
  
  if (phase === 'discovery') {
    phaseLabel = "Discovery Phase (Index Page Crawl)";
    phaseColor = "bg-sky-500/10 text-sky-400 border border-sky-500/25";
    barColor = "from-sky-500 to-sky-400";
  } else if (phase === 'harvesting') {
    phaseLabel = "Enrichment Phase (Sequential Page Harvest)";
    phaseColor = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25";
    barColor = "from-emerald-500 to-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.3)]";
  }

  return (
    <div className="bg-slate-900/90 backdrop-blur-2xl border border-slate-800/80 rounded-2xl p-6 shadow-2xl space-y-4 animate-fadeIn my-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <div className="animate-spin w-4 h-4 border-2 border-emerald-400 border-t-transparent rounded-full" />
            <h3 className="text-sm font-bold text-slate-200">Active Scraping Session</h3>
            <span className={`text-2xs px-2 py-0.5 rounded-full font-bold uppercase tracking-wider ${phaseColor}`}>
              {phaseLabel}
            </span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed font-medium">
            {scrapingStatus || "Connecting to background scraper worker..."}
          </p>
        </div>
        <div className="text-right shrink-0">
          <span className="text-lg font-black text-emerald-400 font-mono tracking-tight">{pct}%</span>
          <span className="text-2xs text-text-muted block font-semibold">{current} / {total} Completed</span>
        </div>
      </div>

      {/* Progress Bar Container */}
      <div className="w-full bg-slate-950/80 h-3 rounded-full overflow-hidden p-0.5 border border-slate-850 shadow-inner">
        <div 
          className={`h-full rounded-full bg-gradient-to-r ${barColor} transition-all duration-500 relative`}
          style={{ width: `${pct}%` }}
        >
          {/* Shine animation */}
          <div className="absolute inset-0 bg-white/20 animate-pulse" />
        </div>
      </div>

      {/* Time Remaining & Meta Details */}
      <div className="flex items-center justify-between text-xs text-slate-500 font-medium px-1 pt-0.5">
        <div>
          {phase === 'harvesting' && remaining > 0 ? (
            <span className="flex items-center space-x-1">
              <svg className="w-3.5 h-3.5 text-emerald-500/85" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
              <span>Estimated time remaining: <strong className="text-slate-300 font-semibold">{secondsLeft}s</strong></span>
            </span>
          ) : phase === 'harvesting' ? (
            <span className="text-emerald-400 font-bold">Finalizing session...</span>
          ) : phase === 'discovery' ? (
            <span className="text-sky-400">Discovering listings on index pages...</span>
          ) : (
            <span className="text-slate-400">Connecting to scraper worker...</span>
          )}
        </div>
        <div className="text-2xs text-slate-600 font-bold uppercase tracking-wider select-none">
          Live Scraper
        </div>
      </div>
    </div>
  );
}
