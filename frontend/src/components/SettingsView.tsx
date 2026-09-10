/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { Button } from './ui/Button';
import { Input } from './ui/Input';

interface SettingsViewProps {
  onBack: () => void;
}

export default function SettingsView({ onBack }: SettingsViewProps) {
  const { t } = useTranslation();
  const [interval, setIntervalVal] = useState<number>(10);
  const [autoAiEval, setAutoAiEval] = useState<boolean>(true);
  const [fullFetchOnStartup, setFullFetchOnStartup] = useState<boolean>(false);
  const [delayBetweenPages, setDelayBetweenPages] = useState<number>(0.25);
  const [delayBetweenListings, setDelayBetweenListings] = useState<number>(0.25);
  
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [success, setSuccess] = useState<string>('');

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/schedule');
      if (res.ok) {
        const data = await res.json();
        setIntervalVal(data.interval ?? 10);
        setAutoAiEval(data.autoAiEval ?? true);
        setFullFetchOnStartup(data.fullFetchOnStartup ?? false);
        setDelayBetweenPages(data.delayBetweenPages ?? 0.25);
        setDelayBetweenListings(data.delayBetweenListings ?? 0.25);
      } else {
        setError(t('settings.fetchError'));
      }
    } catch (err) {
      console.error(err);
      setError(`${t('settings.networkError')} (${t('settings.fetchError')})`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    
    try {
      const res = await fetch('/api/schedule', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          interval,
          autoAiEval,
          fullFetchOnStartup,
          delayBetweenPages,
          delayBetweenListings,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setIntervalVal(data.config.interval);
        setAutoAiEval(data.config.autoAiEval);
        setFullFetchOnStartup(data.config.fullFetchOnStartup);
        setDelayBetweenPages(data.config.delayBetweenPages ?? 0.25);
        setDelayBetweenListings(data.config.delayBetweenListings ?? 0.25);
        setSuccess(t('settings.saveSuccess'));
        setTimeout(() => setSuccess(''), 4000);
      } else {
        const errData = await res.json();
        setError(errData.error || t('settings.saveError'));
      }
    } catch (err) {
      console.error(err);
      setError(`${t('settings.networkError')} (${t('settings.saveError')})`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl mx-auto w-full animate-fadeIn py-4">
      {/* Header Bar */}
      <div className="flex items-center space-x-3 pb-4 border-b border-slate-800">
        <Button
          type="button"
          variant="badge"
          size="sm"
          onClick={onBack}
        >
          <span className="mr-1">←</span>
          <span>{t('common.backToCampaigns')}</span>
        </Button>
        <span className="text-slate-750 font-semibold select-none">|</span>
        <h2 className="text-base font-bold text-slate-200 tracking-tight">{t('settings.title')}</h2>
      </div>

      {loading ? (
        <div className="bg-slate-900/40 backdrop-blur-xl border border-slate-800/80 rounded-2xl p-12 text-center shadow-lg">
          <div className="animate-spin w-8 h-8 border-3 border-emerald-400 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-xs text-slate-400 font-medium">{t('common.loading')}</p>
        </div>
      ) : (
        <form onSubmit={handleSave} className="bg-slate-900/50 backdrop-blur-xl border border-slate-800/85 rounded-3xl p-8 shadow-2xl space-y-6 relative overflow-hidden">
          <div className="absolute -right-20 -top-20 w-44 h-44 rounded-full bg-emerald-500/5 blur-3xl pointer-events-none" />
          <div className="absolute -left-20 -bottom-20 w-44 h-44 rounded-full bg-sky-500/5 blur-3xl pointer-events-none" />

          <div className="space-y-1">
            <span className="text-2xs bg-emerald-500/10 text-emerald-400 font-bold px-2.5 py-0.5 rounded uppercase tracking-wider w-fit block mb-1">
              {t('settings.schedulerConfig')}
            </span>
            <h3 className="text-lg font-bold text-slate-200 font-sans tracking-tight">{t('settings.scraperRules')}</h3>
            <p className="text-xs text-slate-400 leading-relaxed font-semibold">
              {t('settings.rulesDesc')}
            </p>
          </div>

          {error && (
            <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs text-rose-400 font-semibold flex items-center space-x-2 animate-fadeIn">
              <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {success && (
            <div className="p-3.5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-xs text-emerald-400 font-semibold flex items-center space-x-2 animate-fadeIn">
              <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{success}</span>
            </div>
          )}

          <div className="space-y-5 pt-2">
            {/* Scraping Frequency */}
            <div className="space-y-1.5">
              <label htmlFor="scraper-interval-input" className="text-2xs text-slate-400 font-bold uppercase tracking-wider block">
                {t('settings.crawlFrequency')}
              </label>
              <div className="relative">
                <Input
                  id="scraper-interval-input"
                  type="number"
                  min="1"
                  max="1440"
                  required
                  value={interval}
                  onChange={(e) => setIntervalVal(Math.max(1, parseInt(e.target.value, 10) || 1))}
                  className="font-mono pr-12"
                />
                <div className="absolute right-4 top-3 text-2xs text-slate-500 font-bold uppercase tracking-widest pointer-events-none select-none">
                  min
                </div>
              </div>
              <span className="text-2xs text-text-muted block leading-normal">
                {t('settings.frequencyDesc')}
              </span>
            </div>

            {/* Separator */}
            <div className="h-px bg-slate-800/80" />

            {/* Delay Between Search Pages */}
            <div className="space-y-1.5">
              <label htmlFor="scraper-delay-pages-input" className="text-2xs text-slate-400 font-bold uppercase tracking-wider block">
                {t('settings.delayBetweenPages')}
              </label>
              <div className="relative">
                <Input
                  id="scraper-delay-pages-input"
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={delayBetweenPages}
                  onChange={(e) => setDelayBetweenPages(Math.max(0, parseFloat(e.target.value) || 0))}
                  className="font-mono pr-12"
                />
                <div className="absolute right-4 top-3 text-2xs text-slate-500 font-bold uppercase tracking-widest pointer-events-none select-none">
                  sec
                </div>
              </div>
              <span className="text-2xs text-text-muted block leading-normal">
                {t('settings.delayPagesDesc')}
              </span>
            </div>

            {/* Separator */}
            <div className="h-px bg-slate-800/80" />

            {/* Delay Between Listings Details */}
            <div className="space-y-1.5">
              <label htmlFor="scraper-delay-listings-input" className="text-2xs text-slate-400 font-bold uppercase tracking-wider block">
                {t('settings.delayBetweenListings')}
              </label>
              <div className="relative">
                <Input
                  id="scraper-delay-listings-input"
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={delayBetweenListings}
                  onChange={(e) => setDelayBetweenListings(Math.max(0, parseFloat(e.target.value) || 0))}
                  className="font-mono pr-12"
                />
                <div className="absolute right-4 top-3 text-2xs text-slate-500 font-bold uppercase tracking-widest pointer-events-none select-none">
                  sec
                </div>
              </div>
              <span className="text-2xs text-text-muted block leading-normal">
                {t('settings.delayListingsDesc')}
              </span>
            </div>

            {/* Separator */}
            <div className="h-px bg-slate-800/80" />

            {/* Toggle: Auto AI Matcher */}
            <div className="flex items-start justify-between space-x-4 py-1">
              <div className="space-y-0.5">
                <label htmlFor="scraper-auto-ai-toggle" className="text-xs font-bold text-slate-200 block cursor-pointer">
                  {t('settings.autoAiLabel')}
                </label>
                <span className="text-2xs text-slate-500 block leading-normal max-w-md">
                  {t('settings.autoAiDesc')}
                </span>
              </div>
              <button
                id="scraper-auto-ai-toggle"
                type="button"
                role="switch"
                aria-checked={autoAiEval}
                onClick={() => setAutoAiEval(!autoAiEval)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-250 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-500/50 ${
                  autoAiEval ? 'bg-emerald-500' : 'bg-slate-800'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-slate-100 shadow-md ring-0 transition duration-250 ease-in-out ${
                    autoAiEval ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* Separator */}
            <div className="h-px bg-slate-800/80" />

            {/* Toggle: Full Fetch on Startup */}
            <div className="flex items-start justify-between space-x-4 py-1">
              <div className="space-y-0.5">
                <label htmlFor="scraper-startup-fetch-toggle" className="text-xs font-bold text-slate-200 block cursor-pointer">
                  {t('settings.fullCrawlLabel')}
                </label>
                <span className="text-2xs text-text-muted block leading-normal max-w-md">
                  {t('settings.fullCrawlDesc')}
                </span>
              </div>
              <button
                id="scraper-startup-fetch-toggle"
                type="button"
                role="switch"
                aria-checked={fullFetchOnStartup}
                onClick={() => setFullFetchOnStartup(!fullFetchOnStartup)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-250 ease-in-out focus:outline-none focus:ring-2 focus:ring-emerald-500/50 ${
                  fullFetchOnStartup ? 'bg-emerald-500' : 'bg-slate-800'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-slate-100 shadow-md ring-0 transition duration-250 ease-in-out ${
                    fullFetchOnStartup ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          <div className="pt-4 flex space-x-3">
            <Button
              type="submit"
              variant="primary"
              loading={saving}
              className="flex-1 uppercase tracking-wider text-xs py-3"
            >
              {t('settings.scraperRules')}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={onBack}
              className="px-5 py-3 uppercase tracking-wider text-xs"
            >
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
