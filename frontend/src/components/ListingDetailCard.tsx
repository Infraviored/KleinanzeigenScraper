import { useState } from 'react';
import type { Listing } from '../types';
import { useTranslation } from '../hooks/useTranslation';
import type { TranslationPath } from '../i18n/translations';
import { Button } from './ui/Button';
import { Card } from './ui/Card';
import { 
  ChevronLeft, 
  ChevronRight, 
  Sparkles, 
  AlertTriangle, 
  CheckCircle2, 
  RefreshCw, 
  Calendar, 
  MapPin, 
  Copy, 
  Check, 
  ExternalLink,
  Info,
  AlertCircle
} from 'lucide-react';
import { cn } from '../utils/cn';

interface ListingDetailCardProps {
  l: Listing;
  activeProcessingListingIds: string[];
  handleProcessSingleListing: (id: string) => void;
  selectedListingId: string | null;
  setSelectedListingId: (id: string | null) => void;
  mode?: 'list' | 'detail';
}

export default function ListingDetailCard({
  l,
  activeProcessingListingIds,
  handleProcessSingleListing,
  selectedListingId,
  setSelectedListingId,
  mode = 'detail'
}: ListingDetailCardProps) {
  const { t, lang } = useTranslation();
  const [activeImageIndex, setActiveImageIndex] = useState(0);
  const [copiedOutreach, setCopiedOutreach] = useState(false);

  const handlePrevImage = (maxImages: number) => {
    setActiveImageIndex(prev => (prev - 1 + maxImages) % maxImages);
  };

  const handleNextImage = (maxImages: number) => {
    setActiveImageIndex(prev => (prev + 1) % maxImages);
  };

  const handleCopyOutreach = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedOutreach(true);
    setTimeout(() => setCopiedOutreach(false), 2000);
  };

  const isSelected = selectedListingId === l.id;

  // Render Compact List Item Mode
  if (mode === 'list') {
    return (
      <Card 
        onClick={() => setSelectedListingId(isSelected ? null : l.id)}
        className={cn(
          "p-4 cursor-pointer hover:border-brand-accent/30 hover:-translate-y-0.5 transition-all group flex flex-row gap-4 items-stretch",
          isSelected ? "border-brand-accent bg-bg-surface-hover/50 ring-1 ring-brand-accent/20" : "border-border-subtle"
        )}
      >
        {/* Left: Small Thumbnail image */}
        {l.images && l.images.length > 0 ? (
          <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-xl overflow-hidden bg-bg-input border border-border-subtle shrink-0">
            <img
              src={l.images[0]}
              alt={l.title}
              className="w-full h-full object-cover"
            />
          </div>
        ) : (
          <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-xl bg-bg-input border border-border-subtle shrink-0 flex items-center justify-center">
            <Info className="w-6 h-6 text-text-muted/20" />
          </div>
        )}

        {/* Right: Info */}
        <div className="flex-1 flex flex-col justify-between min-w-0">
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="text-2xs text-emerald-500 font-bold uppercase truncate">{l.campaign_name}</span>
              <div className={cn(
                "text-2xs font-bold px-1.5 py-0.5 rounded border leading-none shrink-0",
                l.niceness_score === undefined || l.niceness_score === null
                  ? 'bg-bg-input text-text-muted border-border-subtle'
                  : l.niceness_score >= 70
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : l.niceness_score >= 40
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  : 'bg-bg-surface text-text-secondary border-border-subtle'
              )}>
                {l.niceness_score === undefined || l.niceness_score === null ? '-' : l.niceness_score}
              </div>
            </div>

            <h3 className="text-xs font-bold text-text-primary line-clamp-1 group-hover:text-brand-accent transition-colors">
              {l.title}
            </h3>

            <div className="text-xs font-bold text-brand-accent">
              {l.price}
            </div>
          </div>

          <div className="flex items-center justify-between text-2xs text-text-muted mt-1">
            <span className="flex items-center gap-0.5 truncate max-w-[120px]">
              <MapPin className="w-2.5 h-2.5 shrink-0" />
              <span className="truncate">{l.location}</span>
            </span>
            <span className="flex items-center gap-0.5">
              <Calendar className="w-2.5 h-2.5 shrink-0" />
              <span>{l.date_string}</span>
            </span>
          </div>
        </div>
      </Card>
    );
  }

  // Render Full Detail Mode
  return (
    <div className="space-y-5 animate-fadeIn">
      {/* Slideshow and Header */}
      <div className="space-y-4">
        {/* Gallery */}
        {l.images && l.images.length > 0 && (
          <div className="relative group/gallery w-full aspect-video rounded-2xl overflow-hidden bg-bg-input border border-border-subtle shadow-lg">
            <img
              src={l.images[activeImageIndex]}
              alt={`Listing visual ${activeImageIndex}`}
              className="w-full h-full object-cover transition-all duration-300 transform group-hover/gallery:scale-102"
            />
            {l.images.length > 1 && (
              <>
                <button
                  onClick={(e) => { e.stopPropagation(); handlePrevImage(l.images!.length); }}
                  className="absolute left-3 top-1/2 -translate-y-1/2 bg-bg-input/85 hover:bg-bg-surface border border-border-subtle text-text-muted hover:text-white w-8 h-8 rounded-full flex items-center justify-center transition-colors focus:outline-none z-10"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); handleNextImage(l.images!.length); }}
                  className="absolute right-3 top-1/2 -translate-y-1/2 bg-bg-input/85 hover:bg-bg-surface border border-border-subtle text-text-muted hover:text-white w-8 h-8 rounded-full flex items-center justify-center transition-colors focus:outline-none z-10"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </>
            )}
          </div>
        )}

        {/* Title Block */}
        <div className="flex flex-col gap-3">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <span className="text-2xs text-text-muted uppercase tracking-wider font-semibold block truncate">
                {l.item_name}
              </span>
              <span className="text-2xs text-emerald-500 font-bold uppercase block">
                {l.campaign_name}
              </span>
              {l.last_description_changed_at && (
                <span className="text-2xs text-text-muted font-mono block mt-1" title="Description last modified">
                  {t('listing.mod', {
                    date: new Date(l.last_description_changed_at).toLocaleString(lang === 'en' ? 'en-US' : 'de-DE', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                      hour12: false
                    })
                  })}
                </span>
              )}
            </div>

            {/* Score and Eval Button */}
            <div className="flex items-center gap-2 shrink-0">
              <div className={cn(
                "text-xs font-bold px-2.5 py-1.5 rounded-xl border leading-none",
                l.niceness_score === undefined || l.niceness_score === null
                  ? 'bg-bg-input text-text-muted border-border-subtle'
                  : l.niceness_score >= 70
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                  : l.niceness_score >= 40
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                  : 'bg-bg-surface text-text-secondary border-border-subtle'
              )}>
                {t('common.score')}: {l.niceness_score === undefined || l.niceness_score === null ? '-' : l.niceness_score}
              </div>

              {(() => {
                const isStale = !l.llm_processed || 
                                !l.last_ai_evaluated_at || 
                                (l.last_description_changed_at && l.last_ai_evaluated_at && l.last_description_changed_at > l.last_ai_evaluated_at);
                
                const buttonStyles = activeProcessingListingIds.includes(l.id)
                  ? 'bg-indigo-500/25 text-indigo-300 border-indigo-400/50 animate-pulse'
                  : isStale
                  ? 'animate-pulse bg-indigo-500/10 text-indigo-400 border-indigo-500/30 hover:bg-indigo-500/20'
                  : 'bg-bg-surface text-text-muted border-border-subtle hover:bg-indigo-500/10 hover:text-indigo-400 hover:border-indigo-500/30';

                return (
                  <Button
                    type="button"
                    variant="badge"
                    size="xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleProcessSingleListing(l.id);
                    }}
                    disabled={activeProcessingListingIds.includes(l.id)}
                    title={l.llm_processed ? (isStale ? t('listing.aiStale') : t('listing.reEvaluate')) : t('listing.evaluateWithAi')}
                    className={cn("flex items-center space-x-1.5", buttonStyles)}
                  >
                    {activeProcessingListingIds.includes(l.id) ? (
                      <div className="animate-spin w-3 h-3 border border-current border-t-transparent rounded-full" />
                    ) : (
                      <span className="flex items-center gap-1">
                        {l.llm_processed ? <RefreshCw className="w-3 h-3" /> : <Sparkles className="w-3 h-3" />}
                        <span>{t('listing.aiEval')}</span>
                      </span>
                    )}
                  </Button>
                );
              })()}
            </div>
          </div>

          <div>
            <h2 className="text-base font-bold text-text-primary leading-snug">{l.title}</h2>
            <div className="flex flex-wrap items-center gap-2.5 text-xs font-semibold text-text-muted mt-1.5">
              <span className="text-brand-accent font-bold text-sm">{l.price}</span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5" />
                <span>{l.location}</span>
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Calendar className="w-3.5 h-3.5" />
                <span>{l.date_string}</span>
              </span>
            </div>
          </div>
        </div>

        {/* Specs Metadata Tags */}
        <div className="flex flex-wrap gap-1.5">
          {l.year && (
            <span className="text-2xs bg-bg-input text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-semibold">
              {t('listing.year', { year: l.year })}
            </span>
          )}
          {l.mileage && (
            <span className="text-2xs bg-bg-input text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-semibold">
              {l.mileage}
            </span>
          )}
          {l.cubic_capacity && (
            <span className="text-2xs bg-bg-input text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-semibold font-mono">
              {l.cubic_capacity}
            </span>
          )}

          {/* AI checklist tags */}
          {l.llm_processed && l.criteria_evaluations && l.criteria_evaluations.map((evalItem, idx) => {
            if (evalItem.status === 'satisfied') {
              return (
                <span key={`sat-${idx}`} className="text-2xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                  <span>{evalItem.name}</span>
                </span>
              );
            }
            if (evalItem.status === 'violated') {
              return (
                <span key={`viol-${idx}`} className="text-2xs bg-rose-500/10 text-rose-400 border border-rose-500/20 px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3 text-rose-400" />
                  <span>{evalItem.name}</span>
                </span>
              );
            }
            return null;
          })}

          {/* Needs Re-Eval tag */}
          {l.llm_processed && l.criteria_evaluations?.some(e => e.status === 'Needs Re-Evaluation') && (
            <span className="text-2xs bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1 animate-pulse">
              <AlertTriangle className="w-3 h-3 text-amber-500" />
              <span>{t('listing.needsReEval')}</span>
            </span>
          )}
        </div>

        {/* Description Section */}
        <div className="bg-bg-input/30 p-4 rounded-xl border border-border-subtle">
          <h4 className="text-xs font-bold text-text-muted mb-2 font-mono uppercase tracking-wider">{t('common.description')}</h4>
          <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap font-sans">
            {l.description ? l.description : t('listing.awaitingScraper')}
          </p>
        </div>
      </div>

      {/* AI Evaluations */}
      {l.llm_processed && (
        <div className="space-y-4 pt-2 border-t border-border-subtle">
          {/* Warnings Banner */}
          {l.highlights && l.highlights.some(h => h.sentiment === 'negative') && (
            <div className="bg-rose-500/10 border border-rose-500/25 p-4 rounded-xl space-y-2 animate-fadeIn">
              <span className="text-2xs font-bold text-rose-400 uppercase tracking-wider block font-mono flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-rose-400" />
                {t('listing.highPriorityWarnings')}
              </span>
              <div className="flex flex-wrap gap-2">
                {l.highlights.filter(h => h.sentiment === 'negative').map((h, idx) => (
                  <span key={idx} title={`Evidence: "${h.evidence_quote}"`} className="text-2xs bg-rose-500/20 text-rose-300 px-2.5 py-1 rounded-lg font-semibold border border-rose-500/20">
                    {h.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Highlights */}
          {l.highlights && l.highlights.length > 0 && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-3">
              <span className="text-2xs font-bold text-indigo-400 uppercase tracking-wider block font-mono">
                {t('listing.specialHighlights')}
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {l.highlights.map((h, idx) => {
                  let colorClasses = 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20';
                  let HighlightIcon = Info;
                  if (h.sentiment === 'positive') {
                    colorClasses = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
                    HighlightIcon = CheckCircle2;
                  } else if (h.sentiment === 'negative') {
                    colorClasses = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
                    HighlightIcon = AlertCircle;
                  }
                  return (
                    <div key={idx} className={cn("text-2xs border p-3 rounded-xl flex flex-col gap-1.5", colorClasses)}>
                      <div className="flex justify-between items-center font-bold">
                        <span className="flex items-center gap-1">
                          <HighlightIcon className="w-3.5 h-3.5 shrink-0" />
                          {h.label}
                        </span>
                        <span className="text-2xs uppercase opacity-75">{h.type} ({h.confidence})</span>
                      </div>
                      {h.evidence_quote && (
                        <p className="text-2xs opacity-80 italic leading-normal border-t border-current/10 pt-1.5 mt-0.5">
                          "{h.evidence_quote}"
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* AI Match Summary Text */}
          <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-1.5">
            <span className="text-2xs font-bold text-emerald-400 uppercase tracking-wider block font-mono">
              {t('listing.aiMatchSummary')}
            </span>
            <p className="text-text-secondary leading-relaxed font-sans">{l.summary}</p>
          </div>

          {/* Soft Dimensions Sliders */}
          {l.dimensions && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-3">
              <span className="text-2xs font-bold text-indigo-400 uppercase tracking-wider block font-mono">
                {t('listing.softDimensions')}
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {Object.entries(l.dimensions).map(([key, dim]) => {
                  const label = t(`listing.dimensions.${key}` as TranslationPath) || key;
                  const score = dim.score;
                  const reasoning = dim.reasoning;
                  
                  const isSuspicion = key === 'hiddenRiskSuspicion';
                  const percentage = ((score - 1) / 4) * 100;
                  
                  const barColor = isSuspicion
                    ? (score >= 4 ? 'bg-rose-500' : score >= 3 ? 'bg-amber-500' : 'bg-emerald-500')
                    : (score >= 4 ? 'bg-emerald-500' : score >= 3 ? 'bg-amber-500' : 'bg-rose-500');

                  return (
                    <div key={key} className="space-y-1.5">
                      <div className="flex justify-between items-center text-2xs font-semibold text-text-secondary">
                        <span>{label}</span>
                        <span className="font-bold font-mono">{score}/5</span>
                      </div>
                      <div className="w-full bg-bg-input rounded-full h-1.5 overflow-hidden border border-border-subtle relative">
                        <div 
                          className={cn("h-full transition-all duration-500 shadow-inner", barColor)}
                          style={{ width: `${percentage}%` }} 
                        />
                      </div>
                      {reasoning && (
                        <p className="text-2xs text-text-muted font-sans leading-normal">{reasoning}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Reference Anchor Comparison */}
          {l.reference_comparison && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-2xs font-bold text-teal-400 uppercase tracking-wider block font-mono">
                  {t('listing.referenceComparison')}
                </span>
                <span className={cn(
                  "text-2xs font-bold px-2 py-0.5 rounded-md border",
                  l.reference_comparison.closer_to === 'good'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : l.reference_comparison.closer_to === 'bad'
                    ? 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                    : 'bg-bg-surface text-text-muted border-border-subtle'
                )}>
                  {t('listing.closerTo', { type: l.reference_comparison.closer_to.toUpperCase() })}
                </span>
              </div>
              {l.reference_comparison.reasoning && (
                <p className="text-text-secondary font-sans text-2xs leading-relaxed italic bg-bg-input/30 p-3 rounded-xl border border-border-subtle">
                  "{l.reference_comparison.reasoning}"
                </p>
              )}
            </div>
          )}

          {/* Unified Fields Table */}
          {l.field_evaluations && l.field_evaluations.length > 0 && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-2">
              <span className="text-2xs font-bold text-teal-500 uppercase tracking-wider block font-mono">
                {t('common.extractedFields')}
              </span>
              <div className="divide-y divide-border-subtle">
                {l.field_evaluations.map((item, idx) => {
                  const valStr = item.extracted.value === null || item.extracted.value === undefined
                    ? 'Not specified'
                    : String(item.extracted.value);

                  let statusColor = 'bg-bg-surface text-text-muted border-border-subtle';
                  let statusText = item.status.toUpperCase();

                  if (item.status === 'satisfied') {
                    statusColor = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
                  } else if (item.status === 'partial') {
                    statusColor = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
                  } else if (item.status === 'violated') {
                    statusColor = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
                  } else if (item.status === 'missing_critical') {
                    statusColor = 'bg-rose-500/20 text-rose-300 border-rose-500/30 font-extrabold animate-pulse';
                    statusText = 'CRITICAL GAP';
                  }

                  return (
                    <div key={idx} className="flex justify-between items-start py-2.5 font-sans">
                      <div className="pr-3 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-text-secondary text-xs">{item.field.label}</span>
                          <span className="text-2xs font-mono px-1.5 py-0.5 rounded bg-bg-input border border-border-subtle text-text-muted">
                            {item.field.type}
                            {item.field.unit ? ` (${item.field.unit})` : ''}
                          </span>
                        </div>
                        <div className="text-xs font-semibold text-brand-accent">
                          {t('common.extracted')}: <span className="font-mono">{valStr}</span>
                        </div>
                        {item.extracted.reasoning && (
                          <span className="text-2xs text-text-muted block leading-normal">{item.extracted.reasoning}</span>
                        )}
                        {item.extracted.evidence_quote && (
                          <span className="text-2xs italic text-text-muted/80 block leading-normal">
                            "{item.extracted.evidence_quote}"
                          </span>
                        )}
                      </div>
                      <span className={cn("text-2xs font-bold px-2 py-0.5 rounded border shrink-0", statusColor)}>
                        {statusText}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Checklist Table */}
          {(!l.field_evaluations || l.field_evaluations.length === 0) && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-2">
              <span className="text-2xs font-bold text-teal-500 uppercase tracking-wider block font-mono">
                {t('dashboard.checklist')}
              </span>
              <div className="divide-y divide-border-subtle">
                {l.criteria_evaluations && l.criteria_evaluations.map((evalItem, idx) => (
                  <div key={idx} className="flex justify-between items-start py-2.5 font-sans">
                    <div className="pr-3">
                      <span className="font-bold text-text-secondary text-xs">{evalItem.name}</span>
                      <span className="text-2xs text-text-muted block leading-normal mt-0.5">{evalItem.reasoning}</span>
                    </div>
                    <span className={cn(
                      "text-2xs font-bold px-2 py-0.5 rounded border shrink-0",
                      evalItem.status === 'satisfied' 
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                        : evalItem.status === 'violated' 
                        ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' 
                        : 'bg-bg-surface text-text-muted border-border-subtle'
                    )}>
                      {evalItem.status === 'satisfied' 
                        ? t('listing.satisfied').toUpperCase() 
                        : evalItem.status === 'violated' 
                        ? t('listing.violated').toUpperCase() 
                        : 'NEUTRAL'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}


          {/* Outreach Message */}
          {l.draft_message && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-2">
              <div className="flex justify-between items-center border-b border-border-subtle pb-2">
                <span className="text-2xs font-bold text-emerald-400 uppercase tracking-wider font-mono">
                  {t('listing.outreachAssistant')}
                </span>
                <Button
                  type="button"
                  variant="mini-slate"
                  size="xs"
                  onClick={() => handleCopyOutreach(l.draft_message || '')}
                  className="font-bold h-7 px-3 text-2xs"
                >
                  <span className="flex items-center gap-1.5">
                    {copiedOutreach ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedOutreach ? t('listing.copiedToClipboard') : t('listing.copyDraft')}</span>
                  </span>
                </Button>
              </div>
              <p className="text-text-secondary leading-relaxed font-sans italic text-xs bg-bg-input/65 p-3 rounded-lg border border-border-subtle select-all whitespace-pre-wrap">
                {l.draft_message}
              </p>
            </div>
          )}
        </div>
      )}

      {/* External Link Footer */}
      <div className="pt-4 border-t border-border-subtle flex justify-end">
        <a
          href={l.url}
          target="_blank"
          rel="noreferrer"
          className="text-xs text-brand-accent hover:text-[#f09587] font-bold transition-colors flex items-center gap-1"
        >
          <span>{t('listing.viewOriginal')}</span>
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      </div>
    </div>
  );
}

