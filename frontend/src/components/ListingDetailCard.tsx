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
              <span className="text-xs text-text-muted font-bold truncate">{l.campaign_name}</span>
              <div className={cn(
                "text-xs font-bold px-1.5 py-0.5 rounded border leading-none shrink-0 font-mono",
                l.niceness_score === undefined || l.niceness_score === null
                  ? 'bg-bg-input text-text-muted border-border-subtle'
                  : l.niceness_score >= 70
                  ? 'bg-status-good/10 text-status-good border-status-good/20'
                  : l.niceness_score >= 40
                  ? 'bg-bg-surface text-text-secondary border-border-subtle'
                  : 'bg-status-danger/10 text-status-danger border-status-danger/20'
              )}>
                {l.niceness_score === undefined || l.niceness_score === null ? '-' : l.niceness_score}
              </div>
            </div>

            <h3 className="text-sm font-bold text-text-primary line-clamp-1 group-hover:text-brand-accent transition-colors">
              {l.title}
            </h3>

            {/* Price is neutral primary text in font-mono: prices are facts, not positive or negative verdicts */}
            <div className="text-sm font-bold font-mono text-text-primary">
              {l.price}
            </div>
          </div>

          <div className="flex items-center justify-between text-xs text-text-muted mt-1.5">
            <span className="flex items-center gap-1 truncate max-w-[140px]">
              <MapPin className="w-3 h-3 shrink-0" />
              <span className="truncate">{l.location}</span>
            </span>
            <span className="flex items-center gap-1">
              <Calendar className="w-3 h-3 shrink-0" />
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
              <span className="text-xs text-text-muted font-semibold block truncate">
                {l.item_name}
              </span>
              <span className="text-xs text-text-secondary font-bold block">
                {l.campaign_name}
              </span>
              {l.last_description_changed_at && (
                <span className="text-xs text-text-muted font-mono block mt-1" title="Description last modified">
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
                "text-sm font-bold px-3 py-1.5 rounded-xl border leading-none font-mono",
                l.niceness_score === undefined || l.niceness_score === null
                  ? 'bg-bg-input text-text-muted border-border-subtle'
                  : l.niceness_score >= 70
                  ? 'bg-status-good/10 text-status-good border-status-good/20'
                  : l.niceness_score >= 40
                  ? 'bg-bg-surface text-text-secondary border-border-subtle'
                  : 'bg-status-danger/10 text-status-danger border-status-danger/20'
              )}>
                {t('common.score')}: {l.niceness_score === undefined || l.niceness_score === null ? '-' : l.niceness_score}
              </div>

              {(() => {
                const isStale = !l.llm_processed || 
                                !l.last_ai_evaluated_at || 
                                (l.last_description_changed_at && l.last_ai_evaluated_at && l.last_description_changed_at > l.last_ai_evaluated_at);
                
                const buttonStyles = activeProcessingListingIds.includes(l.id)
                  ? 'bg-brand-accent/20 text-brand-accent border-brand-accent/30 animate-pulse'
                  : isStale
                  ? 'animate-pulse bg-brand-accent/10 text-brand-accent border-brand-accent/25 hover:bg-brand-accent/20'
                  : 'bg-bg-surface text-text-muted border-border-subtle hover:text-text-primary hover:bg-bg-surface-hover';

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
                        {l.llm_processed ? <RefreshCw className="w-3.5 h-3.5" /> : <Sparkles className="w-3.5 h-3.5" />}
                        <span>{t('listing.aiEval')}</span>
                      </span>
                    )}
                  </Button>
                );
              })()}
            </div>
          </div>

          <div>
            <h2 className="text-lg font-bold text-text-primary leading-snug">{l.title}</h2>
            <div className="flex flex-wrap items-center gap-2.5 text-sm font-semibold text-text-muted mt-1.5">
              {/* Price is neutral primary text in font-mono: prices are facts, not positive or negative verdicts */}
              <span className="text-text-primary font-bold font-mono text-base">{l.price}</span>
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
            <span className="text-xs bg-bg-input text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-semibold">
              {t('listing.year', { year: l.year })}
            </span>
          )}
          {l.mileage && (
            <span className="text-xs bg-bg-input text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-semibold">
              {l.mileage}
            </span>
          )}
          {l.cubic_capacity && (
            <span className="text-xs bg-bg-input text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-semibold font-mono">
              {l.cubic_capacity}
            </span>
          )}

          {/* AI checklist tags */}
          {l.llm_processed && l.criteria_evaluations && l.criteria_evaluations.map((evalItem, idx) => {
            if (evalItem.status === 'satisfied') {
              return (
                <span key={`sat-${idx}`} className="text-xs bg-status-good/10 text-status-good border border-status-good/20 px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5 text-status-good" />
                  <span>{evalItem.name}</span>
                </span>
              );
            }
            if (evalItem.status === 'violated') {
              return (
                <span key={`viol-${idx}`} className="text-xs bg-status-danger/10 text-status-danger border border-status-danger/20 px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1">
                  <AlertTriangle className="w-3.5 h-3.5 text-status-danger" />
                  <span>{evalItem.name}</span>
                </span>
              );
            }
            return null;
          })}

          {/* Needs Re-Eval tag */}
          {l.llm_processed && l.criteria_evaluations?.some(e => e.status === 'Needs Re-Evaluation') && (
            <span className="text-xs bg-bg-surface text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-semibold flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5 text-text-muted" />
              <span>{t('listing.needsReEval')}</span>
            </span>
          )}
        </div>

        {/* Description Section */}
        <div className="bg-bg-input/30 p-4 rounded-xl border border-border-subtle">
          <h4 className="text-sm font-bold text-text-muted mb-2">{t('common.description')}</h4>
          <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap font-sans">
            {l.description ? l.description : t('listing.awaitingScraper')}
          </p>
        </div>
      </div>

      {/* AI Evaluations */}
      {l.llm_processed && (
        <div className="space-y-4 pt-2 border-t border-border-subtle">
          {/* Warnings Banner */}
          {l.highlights && l.highlights.some(h => h.sentiment === 'negative') && (
            <div className="bg-status-danger/10 border border-status-danger/25 p-4 rounded-xl space-y-2 animate-fadeIn">
              <span className="text-xs font-bold text-status-danger block flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-status-danger" />
                {t('listing.highPriorityWarnings')}
              </span>
              <div className="flex flex-wrap gap-2">
                {l.highlights.filter(h => h.sentiment === 'negative').map((h, idx) => (
                  <span key={idx} title={`Evidence: "${h.evidence_quote}"`} className="text-xs bg-status-danger/20 text-status-danger px-2.5 py-1 rounded-lg font-semibold border border-status-danger/30">
                    {h.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Highlights */}
          {l.highlights && l.highlights.length > 0 && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-3">
              <span className="text-sm font-bold text-text-muted block">
                {t('listing.specialHighlights')}
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {l.highlights.map((h, idx) => {
                  let colorClasses = 'bg-bg-surface text-text-secondary border-border-subtle';
                  let HighlightIcon = Info;
                  if (h.sentiment === 'positive') {
                    colorClasses = 'bg-status-good/10 text-status-good border-status-good/20';
                    HighlightIcon = CheckCircle2;
                  } else if (h.sentiment === 'negative') {
                    colorClasses = 'bg-status-danger/10 text-status-danger border-status-danger/20';
                    HighlightIcon = AlertCircle;
                  }
                  return (
                    <div key={idx} className={cn("text-xs border p-3 rounded-xl flex flex-col gap-1.5", colorClasses)}>
                      <div className="flex justify-between items-center font-bold">
                        <span className="flex items-center gap-1">
                          <HighlightIcon className="w-3.5 h-3.5 shrink-0" />
                          {h.label}
                        </span>
                        <span className="text-xs opacity-75 font-medium">{h.type} ({h.confidence})</span>
                      </div>
                      {h.evidence_quote && (
                        <p className="text-xs opacity-80 italic leading-normal border-t border-current/10 pt-1.5 mt-0.5">
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
            <span className="text-sm font-bold text-text-muted block">
              {t('listing.aiMatchSummary')}
            </span>
            <p className="text-text-secondary leading-relaxed font-sans text-sm">{l.summary}</p>
          </div>

          {/* Soft Dimensions Sliders */}
          {l.dimensions && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-3">
              <span className="text-sm font-bold text-text-muted block">
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
                    ? (score >= 4 ? 'bg-status-danger' : score >= 3 ? 'bg-text-muted' : 'bg-status-good')
                    : (score >= 4 ? 'bg-status-good' : score >= 3 ? 'bg-text-muted' : 'bg-status-danger');

                  return (
                    <div key={key} className="space-y-1.5">
                      <div className="flex justify-between items-center text-xs font-semibold text-text-secondary">
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
                        <p className="text-xs text-text-muted font-sans leading-normal">{reasoning}</p>
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
                <span className="text-sm font-bold text-text-muted block">
                  {t('listing.referenceComparison')}
                </span>
                <span className={cn(
                  "text-xs font-bold px-2 py-0.5 rounded-md border",
                  l.reference_comparison.closer_to === 'good'
                    ? 'bg-status-good/10 text-status-good border-status-good/20'
                    : l.reference_comparison.closer_to === 'bad'
                    ? 'bg-status-danger/10 text-status-danger border-status-danger/20'
                    : 'bg-bg-surface text-text-muted border-border-subtle'
                )}>
                  {t('listing.closerTo', { type: l.reference_comparison.closer_to.toUpperCase() })}
                </span>
              </div>
              {l.reference_comparison.reasoning && (
                <p className="text-text-secondary font-sans text-xs leading-relaxed italic bg-bg-input/30 p-3 rounded-xl border border-border-subtle">
                  "{l.reference_comparison.reasoning}"
                </p>
              )}
            </div>
          )}

          {/* Unified Fields Table */}
          {l.field_evaluations && l.field_evaluations.length > 0 && (
            <div className="bg-bg-input/60 p-4 rounded-xl border border-border-subtle space-y-2">
              <span className="text-sm font-bold text-text-muted block">
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
                    statusColor = 'bg-status-good/10 text-status-good border-status-good/20';
                  } else if (item.status === 'partial') {
                    statusColor = 'bg-bg-surface text-text-secondary border-border-subtle';
                  } else if (item.status === 'violated') {
                    statusColor = 'bg-status-danger/10 text-status-danger border-status-danger/20';
                  } else if (item.status === 'missing_critical') {
                    statusColor = 'bg-status-danger/20 text-status-danger border-status-danger/30 font-extrabold animate-pulse';
                    statusText = 'CRITICAL GAP';
                  }

                  return (
                    <div key={idx} className="flex justify-between items-start py-2.5 font-sans">
                      <div className="pr-3 space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-text-secondary text-sm">{item.field.label}</span>
                          <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-bg-input border border-border-subtle text-text-muted">
                            {item.field.type}
                            {item.field.unit ? ` (${item.field.unit})` : ''}
                          </span>
                        </div>
                        <div className="text-sm font-semibold text-text-primary">
                          {t('common.extracted')}: <span className="font-mono">{valStr}</span>
                        </div>
                        {item.extracted.reasoning && (
                          <span className="text-xs text-text-muted block leading-normal">{item.extracted.reasoning}</span>
                        )}
                        {item.extracted.evidence_quote && (
                          <span className="text-xs italic text-text-muted/80 block leading-normal">
                            "{item.extracted.evidence_quote}"
                          </span>
                        )}
                      </div>
                      <span className={cn("text-xs font-bold px-2 py-0.5 rounded border shrink-0", statusColor)}>
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
              <span className="text-sm font-bold text-text-muted block">
                {t('dashboard.checklist')}
              </span>
              <div className="divide-y divide-border-subtle">
                {l.criteria_evaluations && l.criteria_evaluations.map((evalItem, idx) => (
                  <div key={idx} className="flex justify-between items-start py-2.5 font-sans">
                    <div className="pr-3">
                      <span className="font-bold text-text-secondary text-sm">{evalItem.name}</span>
                      <span className="text-xs text-text-muted block leading-normal mt-0.5">{evalItem.reasoning}</span>
                    </div>
                    <span className={cn(
                      "text-xs font-bold px-2 py-0.5 rounded border shrink-0",
                      evalItem.status === 'satisfied' 
                        ? 'bg-status-good/10 text-status-good border-status-good/20' 
                        : evalItem.status === 'violated' 
                        ? 'bg-status-danger/10 text-status-danger border-status-danger/20' 
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
                <span className="text-sm font-bold text-text-muted">
                  {t('listing.outreachAssistant')}
                </span>
                <Button
                  type="button"
                  variant="quiet"
                  size="sm"
                  onClick={() => handleCopyOutreach(l.draft_message || '')}
                  className="font-bold"
                >
                  <span className="flex items-center gap-1.5">
                    {copiedOutreach ? <Check className="w-4 h-4 text-status-good" /> : <Copy className="w-4 h-4" />}
                    <span>{copiedOutreach ? t('listing.copiedToClipboard') : t('listing.copyDraft')}</span>
                  </span>
                </Button>
              </div>
              <p className="text-text-secondary leading-relaxed font-sans italic text-sm bg-bg-input/65 p-3.5 rounded-xl border border-border-subtle select-all whitespace-pre-wrap">
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

