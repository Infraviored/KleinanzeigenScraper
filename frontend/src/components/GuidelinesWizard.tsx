import { useState } from 'react'
import type { SampleListing } from '../types'
import { useTranslation } from '../hooks/useTranslation'
import { Button } from './ui/Button'
import { Clipboard, Check, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'

interface GuidelinesWizardProps {
  activeSearchTarget: {
    id?: number
    name: string
    url: string
    knowledge_set_id?: number | null
  }
  marketMemo: string
  setMarketMemo: (memo: string) => void
  sampledListings: SampleListing[]
  sampledListingsLoading: boolean
  fetchSampleListings: (searchId: number) => Promise<void>
  researcherOutput: string
  setResearcherOutput: (output: string) => void
  researchPromptTemplate: string
  marketPromptTemplate: string
  profilePromptTemplate: string
  editKsError: string
  wizardStep: 1 | 2 | 3
  setWizardStep: (step: 1 | 2 | 3) => void
  handleSaveKnowledgeSet: () => Promise<void>
  parsedExpertKnowledge: string
  parsedGoodRef: string
  parsedBadRef: string
  parsedDemoMsg: string
  parsedItemJson: string
  isScraping: boolean
  scrapingStatus: string
  scrapingProgress: { phase: string; current: number; total: number; status: string; } | null
}

// Helper to parse target search URL for buyer context attributes
function parseKleinanzeigenUrl(url: string, name: string) {
  let maxPrice = 'Any';
  const priceMatch = url.match(/preis:(?:\d*):(\d+)/) || url.match(/preis::(\d+)/);
  if (priceMatch && priceMatch[1]) {
    maxPrice = priceMatch[1] + ' Euro';
  }

  let maxMileage = 'Any';
  const decodedUrl = decodeURIComponent(url);
  const kmMatch = decodedUrl.match(/km_i:(?:\d*),(\d+)/) || decodedUrl.match(/km_i:,(\d+)/) || decodedUrl.match(/km_i:(\d+)/);
  if (kmMatch && kmMatch[1]) {
    maxMileage = kmMatch[1] + ' km';
  }

  let query = 'Used product';
  const cleanedName = name.replace(/\s*Settings\s*/gi, '').trim();
  if (cleanedName) {
    query = cleanedName;
  }

  return {
    query,
    maxMileage,
    maxPrice
  };
}

export default function GuidelinesWizard({
  activeSearchTarget,
  marketMemo,
  setMarketMemo,
  sampledListings,
  sampledListingsLoading,
  fetchSampleListings,
  researcherOutput,
  setResearcherOutput,
  researchPromptTemplate,
  marketPromptTemplate,
  profilePromptTemplate,
  editKsError,
  handleSaveKnowledgeSet,
  parsedExpertKnowledge,
  parsedGoodRef,
  parsedBadRef,
  parsedDemoMsg,
  parsedItemJson,
  isScraping,
  scrapingStatus,
  scrapingProgress,
  wizardStep,
  setWizardStep
}: GuidelinesWizardProps) {
  const { t } = useTranslation()
  const [copiedPromptId, setCopiedPromptId] = useState<string | null>(null)
  
  // Progressive return box disclosure states
  const [showStep1Next, setShowStep1Next] = useState(false)
  const [showStep2Return, setShowStep2Return] = useState(false)
  const [showStep3Return, setShowStep3Return] = useState(false)

  // Copy helper
  const handleCopyPrompt = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedPromptId(id)
    setTimeout(() => setCopiedPromptId(null), 2000)
    
    // Auto-reveal the respective return field/action
    if (id === 'prompt-research') {
      setShowStep1Next(true)
    } else if (id === 'prompt-market') {
      setShowStep2Return(true)
    } else if (id === 'prompt-profile') {
      setShowStep3Return(true)
    }
  }

  // Compile Research prompt (Prompt 1)
  const getResearchPromptWithContext = () => {
    if (!researchPromptTemplate) return 'Loading...'
    const parsed = parseKleinanzeigenUrl(activeSearchTarget?.url || '', activeSearchTarget?.name || '')
    const buyerContext = `Search Query: ${parsed.query}\nMax Mileage: ${parsed.maxMileage}\nMax Price: ${parsed.maxPrice}`
    return researchPromptTemplate
      .replace('{{USER_CONTEXT}}', buyerContext)
  }

  // Compile Market memo generation prompt (Prompt 2)
  const getMarketPromptWithContext = () => {
    if (!marketPromptTemplate) return 'Loading...'
    const sampledStr = sampledListings.map((s, idx) => (
      `=== Sample #${idx + 1} ===\nTitle: ${s.title}\nDetails: ${s.details || ''}\nDescription:\n${s.description}\n`
    )).join('\n')
    const parsed = parseKleinanzeigenUrl(activeSearchTarget?.url || '', activeSearchTarget?.name || '')
    const buyerContext = `Search Query: ${parsed.query}\nMax Mileage: ${parsed.maxMileage}\nMax Price: ${parsed.maxPrice}`
    return marketPromptTemplate
      .replace('{{USER_CONTEXT}}', buyerContext)
      .replace('{{SAMPLED_LISTINGS}}', sampledStr || 'No sampled listings available.')
  }

  // Compile Guidelines Profile synthesis prompt (Prompt 3)
  const getProfilePromptWithContext = () => {
    if (!profilePromptTemplate) return 'Loading...'
    const parsed = parseKleinanzeigenUrl(activeSearchTarget?.url || '', activeSearchTarget?.name || '')
    const buyerContext = `Search Query: ${parsed.query}\nMax Mileage: ${parsed.maxMileage}\nMax Price: ${parsed.maxPrice}`
    return profilePromptTemplate
      .replace('{{USER_CONTEXT}}', buyerContext)
      .replace('{{MARKET_MEMO}}', marketMemo || 'No market memo provided.')
  }

  const [expandedIndex, setExpandedIndex] = useState<number | null>(null)

  return (
    <div className="space-y-6 w-full">
      {/* Step Indicator Header */}
      {/* min-w-0 on the cells below matters: a grid column is at least its own
          min-content by default, so the three labels together demanded more
          than the container had and the third was clipped off the edge at
          phone width. */}
      <div className="grid grid-cols-3 w-full border border-border-subtle rounded-xl overflow-hidden bg-bg-input/60">
        <button
          onClick={() => setWizardStep(1)}
          className={`min-w-0 px-2 py-3.5 text-sm sm:text-base font-bold leading-snug break-words transition-all text-center border-b-2 ${
            wizardStep === 1
              ? 'border-brand-accent text-brand-accent bg-bg-surface/40'
              : 'border-transparent text-text-muted hover:text-text-secondary hover:bg-bg-surface/20'
          }`}
        >
          {t('wizard.step1Tab')}
        </button>
        <button
          onClick={() => (showStep1Next || showStep2Return || marketMemo.trim()) && setWizardStep(2)}
          disabled={!(showStep1Next || showStep2Return || marketMemo.trim())}
          className={`min-w-0 px-2 py-3.5 text-sm sm:text-base font-bold leading-snug break-words transition-all text-center border-b-2 disabled:opacity-30 disabled:cursor-not-allowed ${
            wizardStep === 2
              ? 'border-brand-accent text-brand-accent bg-bg-surface/40'
              : 'border-transparent text-text-muted hover:text-text-secondary hover:bg-bg-surface/20'
          }`}
        >
          {t('wizard.step2Tab')}
        </button>
        <button
          onClick={() => marketMemo.trim().length > 0 && setWizardStep(3)}
          disabled={!marketMemo.trim()}
          className={`min-w-0 px-2 py-3.5 text-sm sm:text-base font-bold leading-snug break-words transition-all text-center border-b-2 disabled:opacity-30 disabled:cursor-not-allowed ${
            wizardStep === 3
              ? 'border-brand-accent text-brand-accent bg-bg-surface/40'
              : 'border-transparent text-text-muted hover:text-text-secondary hover:bg-bg-surface/20'
          }`}
        >
          {t('wizard.step3Tab')}
        </button>
      </div>

      {/* SINGLE COLUMN STEP CONTENT WORKSPACE */}
      <div className="bg-bg-surface/20 border border-border-subtle rounded-2xl p-5 min-h-[300px]">
        
        {/* STEP 1: DEEP RESEARCH */}
        {wizardStep === 1 && (
          <div className="space-y-5 animate-fadeIn">
            <div className="pb-4 border-b border-border-subtle space-y-1">
              <h3 className="text-xl sm:text-2xl font-bold text-text-primary">{t('wizard.step1Title')}</h3>
              <p className="text-base text-text-secondary leading-relaxed pt-1">
                {t('wizard.step1Desc')}
              </p>
            </div>

            <div className="space-y-2">
              <div className="bg-[#000e0e] border border-border-subtle rounded-xl overflow-hidden shadow-2xl">
                <div className="flex justify-between items-center bg-bg-input/60 px-4 py-2 border-b border-border-subtle/60">
                  <span className="text-sm font-bold text-text-muted">{t('common.promptDeepResearch')}</span>
                  <Button
                    variant="quiet"
                    size="xs"
                    onClick={() => handleCopyPrompt(getResearchPromptWithContext(), 'prompt-research')}
                    className={`font-bold transition-all ${
                      copiedPromptId === 'prompt-research'
                        ? 'bg-status-good/20 text-status-good border-status-good/30'
                        : 'border-border-subtle'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      {copiedPromptId === 'prompt-research' ? <Check className="w-3.5 h-3.5 text-status-good" /> : <Clipboard className="w-3.5 h-3.5" />}
                      <span>{copiedPromptId === 'prompt-research' ? t('wizard.promptCopied') : t('common.copy')}</span>
                    </span>
                  </Button>
                </div>
                <div className="relative">
                  <pre className="w-full p-4 text-sm text-text-secondary font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[240px] overflow-y-auto scrollbar-thin select-all">
                    {getResearchPromptWithContext()}
                  </pre>
                </div>
              </div>
            </div>


            {showStep1Next && (
              <div className="pt-4 border-t border-border-subtle flex justify-end animate-fadeIn">
                <Button
                  variant="primary"
                  onClick={() => setWizardStep(2)}
                  className="font-extrabold py-2.5 px-5 text-sm shadow-md shadow-brand-accent/10 hover:shadow-brand-accent/20 active:scale-98"
                >
                  {t('wizard.proceedToStep2')}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* STEP 2: MARKET CALIBRATION */}
        {wizardStep === 2 && (
          <div className="space-y-5 animate-fadeIn">
            <div className="pb-4 border-b border-border-subtle space-y-1">
              <h3 className="text-xl sm:text-2xl font-bold text-text-primary">{t('wizard.step2Title')}</h3>

              <p className="text-base text-text-secondary leading-relaxed pt-1">
                {t('wizard.step2Desc')}
              </p>
            </div>

            {/* Scraper progress & listing samples context */}
            <div className="space-y-3 bg-bg-input/40 border border-border-subtle rounded-2xl p-4">
              <div className="flex justify-between items-center pb-2 border-b border-border-subtle">
                <span className="text-sm font-bold text-text-muted">{t('wizard.liveMarketSamples')}</span>
                {!sampledListingsLoading && (
                  <Button
                    variant="secondary"
                    size="xs"
                    disabled={isScraping}
                    onClick={() => activeSearchTarget?.id && fetchSampleListings(activeSearchTarget.id)}
                    className="font-bold flex items-center gap-1"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    <span>{t('wizard.refreshSamples')}</span>
                  </Button>
                )}
              </div>

              {isScraping && (
                <div className="bg-status-good/5 border border-status-good/10 rounded-xl p-3 flex flex-col space-y-2">
                  <div className="flex items-center space-x-2 text-sm font-semibold text-status-good">
                    <div className="w-3 h-3 rounded-full border-2 border-status-good border-t-transparent animate-spin" />
                    <span>
                      {scrapingProgress
                        ? t('wizard.crawlingMarketListings', { current: scrapingProgress.current, total: scrapingProgress.total })
                        : scrapingStatus || t('wizard.crawlingFresh')}
                    </span>
                  </div>
                  {scrapingProgress && (
                    <div className="w-full bg-bg-input rounded-full h-1.5 overflow-hidden">
                      <div 
                        className="bg-status-good h-full transition-all duration-300" 
                        style={{ width: `${(scrapingProgress.current / scrapingProgress.total) * 100}%` }}
                      />
                    </div>
                  )}
                </div>
              )}

              {sampledListingsLoading ? (
                <div className="flex items-center justify-center gap-3 py-6 border border-dashed border-border-subtle rounded-xl">
                  <div className="w-3.5 h-3.5 rounded-full border-2 border-status-good border-t-transparent animate-spin" />
                  <span className="text-sm text-text-muted font-semibold">{t('wizard.loadingClassifieds')}</span>
                </div>
              ) : sampledListings.length > 0 ? (
                <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                  {sampledListings.map((s, idx) => {
                    const isExpanded = expandedIndex === idx;
                    return (
                      <div key={s.id || idx} className="bg-bg-input/20 border border-border-subtle rounded-xl p-3 space-y-1.5 hover:border-brand-accent/30 transition-colors">
                        <div 
                          onClick={() => setExpandedIndex(isExpanded ? null : idx)}
                          className="flex justify-between items-center cursor-pointer select-none"
                        >
                          <div className="flex-1 pr-3">
                            <span className="font-bold text-sm text-text-secondary block">#{idx + 1}: {s.title}</span>
                            {s.details && (
                              <span className="text-xs text-text-muted font-mono block mt-0.5">{s.details}</span>
                            )}
                          </div>
                          <span className="text-text-muted transition-transform">
                            {isExpanded ? (
                              <ChevronUp className="w-4 h-4 text-text-muted" />
                            ) : (
                              <ChevronDown className="w-4 h-4 text-text-muted" />
                            )}
                          </span>
                        </div>
                        {isExpanded && (
                          <div className="text-sm text-text-secondary mt-1 border-t border-border-subtle pt-1.5 leading-relaxed whitespace-pre-wrap font-mono bg-bg-input/50 p-2 rounded border border-border-subtle max-h-[120px] overflow-y-auto">
                            {s.description}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>

            <div className="space-y-2">
              <div className="bg-[#000e0e] border border-border-subtle rounded-xl overflow-hidden shadow-2xl">
                <div className="flex justify-between items-center bg-bg-input/60 px-4 py-2 border-b border-border-subtle/60">
                  <span className="text-sm font-bold text-text-muted">{t('common.promptCalibration')}</span>
                  <Button
                    variant="quiet"
                    size="xs"
                    onClick={() => handleCopyPrompt(getMarketPromptWithContext(), 'prompt-market')}
                    className={`font-bold transition-all ${
                      copiedPromptId === 'prompt-market'
                        ? 'bg-status-good/20 text-status-good border-status-good/30'
                        : 'border-border-subtle'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      {copiedPromptId === 'prompt-market' ? <Check className="w-3.5 h-3.5 text-status-good" /> : <Clipboard className="w-3.5 h-3.5" />}
                      <span>{copiedPromptId === 'prompt-market' ? t('wizard.calibrationCopied') : t('common.copy')}</span>
                    </span>
                  </Button>
                </div>
                <div className="relative">
                  <pre className="w-full p-4 text-sm text-text-secondary font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[240px] overflow-y-auto scrollbar-thin select-all">
                    {getMarketPromptWithContext()}
                  </pre>
                </div>
              </div>
            </div>


            {/* Disclosed Return Box */}
            {showStep2Return && (
              <div className="space-y-2 animate-fadeIn border-t border-border-subtle pt-4">
                <label className="block text-sm font-semibold text-text-secondary">{t('wizard.pasteMarketMemo')}</label>
                <textarea
                  value={marketMemo}
                  onChange={e => setMarketMemo(e.target.value)}
                  placeholder={t('wizard.pasteMarketMemoPlaceholder')}
                  rows={8}
                  className="w-full bg-bg-input border border-border-subtle rounded-xl p-3.5 text-sm text-text-secondary font-mono focus:outline-none focus:border-brand-accent whitespace-pre-wrap leading-relaxed shadow-inner placeholder-text-muted/40"
                />
              </div>
            )}

            <div className="pt-4 border-t border-border-subtle flex justify-between">
              <Button
                variant="secondary"
                onClick={() => setWizardStep(1)}
                className="text-sm font-bold py-2.5 px-4"
              >
                {t('wizard.backToStep1')}
              </Button>
              {marketMemo.trim().length > 0 && (
                <Button
                  variant="primary"
                  onClick={() => setWizardStep(3)}
                  className="font-extrabold py-2.5 px-5 text-sm shadow-md shadow-brand-accent/10 hover:shadow-brand-accent/20 active:scale-98 animate-fadeIn"
                >
                  {t('wizard.proceedToStep3')}
                </Button>
              )}
            </div>
          </div>
        )}

        {/* STEP 3: CHECKLIST SYNTHESIS & REACTIVE PREVIEW */}
        {wizardStep === 3 && (
          <div className="space-y-5 animate-fadeIn">
            <div className="pb-4 border-b border-border-subtle space-y-1">
              <h3 className="text-xl sm:text-2xl font-bold text-text-primary">{t('wizard.step3Title')}</h3>
              <p className="text-base text-text-secondary leading-relaxed pt-1">
                {t('wizard.step3Desc')}
              </p>
            </div>

            <div className="space-y-2">
              <div className="bg-[#000e0e] border border-border-subtle rounded-xl overflow-hidden shadow-2xl">
                <div className="flex justify-between items-center bg-bg-input/60 px-4 py-2 border-b border-border-subtle/60">
                  <span className="text-sm font-bold text-text-muted">{t('common.promptSynthesis')}</span>
                  <Button
                    variant="quiet"
                    size="xs"
                    disabled={!marketMemo.trim()}
                    onClick={() => handleCopyPrompt(getProfilePromptWithContext(), 'prompt-profile')}
                    className={`font-bold transition-all ${
                      copiedPromptId === 'prompt-profile'
                        ? 'bg-status-good/20 text-status-good border-status-good/30'
                        : 'border-border-subtle'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      {copiedPromptId === 'prompt-profile' ? <Check className="w-3.5 h-3.5 text-status-good" /> : <Clipboard className="w-3.5 h-3.5" />}
                      <span>{copiedPromptId === 'prompt-profile' ? t('wizard.synthesisCopied') : t('common.copy')}</span>
                    </span>
                  </Button>
                </div>
                <div className="relative">
                  <pre className="w-full p-4 text-sm text-text-secondary font-mono overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-[240px] overflow-y-auto scrollbar-thin select-all">
                    {getProfilePromptWithContext()}
                  </pre>
                </div>
              </div>
            </div>


            {/* Disclosed Return Box */}
            {showStep3Return && (
              <div className="space-y-2 animate-fadeIn border-t border-border-subtle pt-4">
                <label className="block text-sm font-semibold text-text-secondary">{t('wizard.pasteResearcherOutput')}</label>
                <textarea
                  value={researcherOutput}
                  onChange={e => setResearcherOutput(e.target.value)}
                  placeholder={t('wizard.pasteResearcherOutputPlaceholder')}
                  rows={8}
                  className="w-full bg-bg-input border border-border-subtle rounded-xl p-3.5 text-sm text-text-secondary font-mono focus:outline-none focus:border-brand-accent whitespace-pre-wrap leading-relaxed shadow-inner placeholder-text-muted/40"
                />
              </div>
            )}

            {/* REACTIVE LIVE PREVIEW BLOCK */}
            {(parsedExpertKnowledge || parsedGoodRef || parsedBadRef || parsedDemoMsg || parsedItemJson) && (
              <div className="bg-bg-input/60 border border-border-subtle rounded-2xl p-5 space-y-4 mt-6 shadow-2xl animate-fadeIn">
                <div className="border-b border-border-subtle pb-2 flex justify-between items-center">
                  <span className="text-lg font-bold text-text-primary block">{t('wizard.reactivePreview')}</span>
                  <span className="text-sm font-bold bg-status-good/10 text-status-good border border-status-good/20 px-2.5 py-1 rounded">{t('wizard.liveParsed')}</span>
                </div>

                {/* Target & Risk Reference Anchors */}
                {(parsedGoodRef || parsedBadRef) && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {parsedGoodRef && (
                      <div className="bg-bg-input/40 border border-border-subtle rounded-xl p-4 space-y-1.5 shadow-sm">
                        <span className="text-sm bg-status-good/10 text-status-good font-bold px-2.5 py-1 rounded block w-fit">{t('wizard.targetAnchor')}</span>
                        <p className="text-sm text-text-secondary leading-relaxed font-mono whitespace-pre-wrap">{parsedGoodRef}</p>
                      </div>
                    )}

                    {parsedBadRef && (
                      <div className="bg-bg-input/40 border border-border-subtle rounded-xl p-4 space-y-1.5 shadow-sm">
                        <span className="text-sm bg-status-danger/10 text-status-danger font-bold px-2.5 py-1 rounded block w-fit">{t('wizard.riskAnchor')}</span>
                        <p className="text-sm text-text-secondary leading-relaxed font-mono whitespace-pre-wrap">{parsedBadRef}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Outreach Message Starter */}
                {parsedDemoMsg && (
                  <div className="bg-bg-input/40 border border-border-subtle rounded-xl p-4 shadow-sm">
                    <span className="text-sm bg-brand-accent/10 text-brand-accent font-bold px-2.5 py-1 rounded block w-fit mb-1.5">{t('wizard.outreachStarter')}</span>
                    <p className="text-base text-text-secondary leading-relaxed italic font-medium">"{parsedDemoMsg}"</p>
                  </div>
                )}

                {/* Checklist table logic */}
                {parsedItemJson && (() => {
                  try {
                    const parsedObj = JSON.parse(parsedItemJson)
                    const positiveCriteria: { id: string; description?: string; question?: string; market_frequency?: string; importance_hint?: string }[] =
                      parsedObj.explicit_positive_criteria || parsedObj.extraction_criteria || []
                    const negativeCriteria: { id: string; description?: string; question?: string; market_frequency?: string; importance_hint?: string }[] =
                      parsedObj.explicit_negative_criteria || []
                    const highValueUnknowns: { id: string; description?: string; applies_when?: string }[] =
                      parsedObj.high_value_unknown_fields || []

                    const isNewSchema = !!(parsedObj.explicit_positive_criteria || parsedObj.explicit_negative_criteria)
                    const weightsDict = parsedObj.scoring_model?.weights || {}

                    const importanceLabel = (c: { id: string; importance_hint?: string }) => {
                      if (isNewSchema) return c.importance_hint || 'medium'
                      const w = weightsDict[c.id]
                      if (!w) return 'medium'
                      const imp = w.importance ?? 10
                      if (imp >= 20) return 'high'
                      if (imp >= 10) return 'medium'
                      return 'low'
                    }

                    const importanceBadge = (hint: string) => {
                      if (hint === 'high') return 'text-status-good'
                      if (hint === 'low') return 'text-text-muted/40'
                      return 'text-text-muted/80'
                    }

                    return (
                      <div className="space-y-4">
                        {positiveCriteria.length > 0 && (
                          <div className="bg-bg-input/50 border border-border-subtle rounded-xl p-4 space-y-3 shadow-inner">
                            <span className="text-sm bg-status-good/10 text-status-good font-extrabold px-2.5 py-1 rounded block w-fit">{t('wizard.positiveSignals', { count: positiveCriteria.length })}</span>
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-sm border-collapse">
                                <thead>
                                  <tr className="border-b border-border-subtle text-text-muted font-bold text-sm">
                                    <th className="py-2.5 pr-4">{t('wizard.id')}</th>
                                    <th className="py-2.5 pr-4">{t('wizard.signalDescription')}</th>
                                    <th className="py-2.5 pr-4">{t('wizard.importance')}</th>
                                    <th className="py-2.5">{t('wizard.frequency')}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {positiveCriteria.map((c, idx) => {
                                    const hint = importanceLabel(c)
                                    return (
                                      <tr key={idx} className="border-b border-border-subtle/40 hover:bg-bg-surface/10 text-text-secondary">
                                        <td className="py-2.5 pr-4 font-bold font-mono text-sm text-text-secondary">{c.id}</td>
                                        <td className="py-2.5 pr-4 leading-normal">{c.description || c.question}</td>
                                        <td className={`py-2.5 pr-4 font-bold text-sm ${importanceBadge(hint)}`}>{hint}</td>
                                        <td className="py-2.5 font-medium text-sm text-text-muted">{c.market_frequency || 'mixed'}</td>
                                      </tr>
                                    )
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {negativeCriteria.length > 0 && (
                          <div className="bg-bg-input/50 border border-border-subtle rounded-xl p-4 space-y-3 shadow-inner">
                            <span className="text-sm bg-status-danger/10 text-status-danger font-extrabold px-2.5 py-1 rounded block w-fit">{t('wizard.negativeSignals', { count: negativeCriteria.length })}</span>
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-sm border-collapse">
                                <thead>
                                  <tr className="border-b border-border-subtle text-text-muted font-bold text-sm">
                                    <th className="py-2.5 pr-4">{t('wizard.id')}</th>
                                    <th className="py-2.5 pr-4">{t('wizard.riskDescription')}</th>
                                    <th className="py-2.5 pr-4">{t('wizard.importance')}</th>
                                    <th className="py-2.5">{t('wizard.frequency')}</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {negativeCriteria.map((c, idx) => {
                                    const hint = importanceLabel(c)
                                    return (
                                      <tr key={idx} className="border-b border-border-subtle/40 hover:bg-bg-surface/10 text-text-secondary">
                                        <td className="py-2.5 pr-4 font-bold font-mono text-sm text-text-secondary">{c.id}</td>
                                        <td className="py-2.5 pr-4 leading-normal">{c.description || c.question}</td>
                                        <td className={`py-2.5 pr-4 font-bold text-sm ${importanceBadge(hint)}`}>{hint}</td>
                                        <td className="py-2.5 font-medium text-sm text-text-muted">{c.market_frequency || 'mixed'}</td>
                                      </tr>
                                    )
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {highValueUnknowns.length > 0 && (
                          <div className="bg-bg-input/50 border border-border-subtle rounded-xl p-4 space-y-3 shadow-inner">
                            <span className="text-sm bg-bg-surface text-text-muted border border-border-subtle font-extrabold px-2.5 py-1 rounded block w-fit">{t('wizard.highValueUnknowns', { count: highValueUnknowns.length })}</span>
                            <div className="space-y-2">
                              {highValueUnknowns.map((u, idx) => (
                                <div key={idx} className="text-sm text-text-secondary leading-relaxed border-b border-border-subtle/40 pb-2">
                                  <span className="font-bold font-mono text-sm text-text-muted mr-2">{u.id}</span>
                                  <span>{u.description}</span>
                                  {u.applies_when && <span className="block text-xs text-text-muted/60 mt-0.5 italic">{u.applies_when}</span>}
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  } catch {
                    return (
                      <div className="bg-bg-input/50 border border-border-subtle text-text-muted p-4 rounded-xl text-sm font-mono">
                        {t('wizard.waitingSynthesis')}
                      </div>
                    )
                  }
                })()}
              </div>
            )}

            <div className="pt-4 border-t border-border-subtle flex justify-between">
              <Button
                variant="secondary"
                onClick={() => setWizardStep(2)}
                className="text-sm font-bold py-2.5 px-4"
              >
                {t('wizard.backToStep2')}
              </Button>
              
              <Button
                variant="primary"
                onClick={handleSaveKnowledgeSet}
                disabled={!researcherOutput.trim()}
                className="font-extrabold py-3 px-6 text-sm shadow-lg shadow-brand-accent/10 hover:shadow-brand-accent/20 active:scale-98 animate-fadeIn"
              >
                {t('wizard.saveChecklist')}
              </Button>
            </div>
          </div>
        )}
      </div>

      {editKsError && (
        <div className="text-sm text-status-danger font-semibold bg-status-danger/10 p-3.5 rounded-xl border border-status-danger/20">{editKsError}</div>
      )}
    </div>
  )
}
