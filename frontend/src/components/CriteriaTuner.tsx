import type { ParsedKnowledgeConfig } from '../types'
import { useTranslation } from '../hooks/useTranslation'
import { Button } from './ui/Button'

interface CriteriaTunerProps {
  editKsJson: string
  onChange: (newJson: string) => void
}

export default function CriteriaTuner({ editKsJson, onChange }: CriteriaTunerProps) {
  const { t } = useTranslation();
  let parsedConfig: ParsedKnowledgeConfig | null = null;
  try {
    parsedConfig = JSON.parse(editKsJson) as ParsedKnowledgeConfig;
  } catch {
    // Ignore invalid JSON in UI helper
  }

  if (!parsedConfig || !parsedConfig.extraction_criteria || parsedConfig.extraction_criteria.length === 0) {
    return null;
  }

  const weights = parsedConfig.scoring_model?.weights || {};

  const handleUpdateWeight = (criterionId: string, newImportance: number) => {
    if (!parsedConfig) return;
    try {
      const config = { ...parsedConfig };
      if (!config.scoring_model) config.scoring_model = {};
      if (!config.scoring_model.weights) config.scoring_model.weights = {};

      if (!config.scoring_model.weights[criterionId]) {
        const criterion = (config.extraction_criteria || []).find(c => c.id === criterionId);
        config.scoring_model.weights[criterionId] = {
          satisfied_if: criterion?.type === 'boolean' ? true : 1,
          importance: newImportance
        };
      } else {
        config.scoring_model.weights[criterionId].importance = newImportance;
      }
      onChange(JSON.stringify(config, null, 2));
    } catch (e) {
      console.error('Could not update weight inside invalid JSON:', e);
    }
  };

  const handleToggleSatisfiedIf = (criterionId: string) => {
    if (!parsedConfig) return;
    try {
      const config = { ...parsedConfig };
      if (!config.scoring_model) config.scoring_model = {};
      if (!config.scoring_model.weights) config.scoring_model.weights = {};

      const criterion = (config.extraction_criteria || []).find(c => c.id === criterionId);
      const isNumType = criterion?.type === 'number';

      if (!config.scoring_model.weights[criterionId]) {
        config.scoring_model.weights[criterionId] = {
          satisfied_if: isNumType ? 1 : false,
          importance: 0
        };
      } else {
        const current = config.scoring_model.weights[criterionId].satisfied_if;
        if (typeof current === 'boolean') {
          config.scoring_model.weights[criterionId].satisfied_if = !current;
        } else if (typeof current === 'number') {
          config.scoring_model.weights[criterionId].satisfied_if = current === 1 ? 0 : 1;
        } else {
          config.scoring_model.weights[criterionId].satisfied_if = true;
        }
      }
      onChange(JSON.stringify(config, null, 2));
    } catch (e) {
      console.error('Could not toggle satisfied_if inside invalid JSON:', e);
    }
  };

  const handleUpdateSatisfiedIfValue = (criterionId: string, value: unknown) => {
    if (!parsedConfig) return;
    try {
      const config = { ...parsedConfig };
      if (!config.scoring_model) config.scoring_model = {};
      if (!config.scoring_model.weights) config.scoring_model.weights = {};

      if (!config.scoring_model.weights[criterionId]) {
        config.scoring_model.weights[criterionId] = {
          satisfied_if: value,
          importance: 0
        };
      } else {
        config.scoring_model.weights[criterionId].satisfied_if = value;
      }
      onChange(JSON.stringify(config, null, 2));
    } catch (e) {
      console.error('Could not update satisfied_if inside invalid JSON:', e);
    }
  };

  return (
    <div className="bg-slate-950/40 p-5 border border-slate-800 rounded-2xl mt-4 space-y-4">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-900 pb-3 gap-2">
        <div>
          <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider font-mono flex items-center gap-1.5">
            <span>🎛️</span>
            <span>{t('tuner.title')}</span>
          </h4>
          <p className="text-2xs text-slate-500 font-sans mt-0.5">
            {t('tuner.desc')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xs bg-slate-800/50 text-slate-400 border border-slate-700/50 px-2.5 py-1 rounded-lg font-bold font-mono">
            {t('tuner.autoNormalized')}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {parsedConfig.extraction_criteria.map((c: { id: string; description?: string; type?: string }) => {
          const wEntry = weights[c.id];
          const currentImportance = wEntry ? wEntry.importance ?? 0 : 0;
          const satisfiedVal = wEntry ? wEntry.satisfied_if : undefined;

          const resolvedSatisfiedVal = satisfiedVal === undefined
            ? (c.type === 'boolean' ? true : 1)
            : satisfiedVal;

          const percentBadgeColor = currentImportance === 0
            ? 'text-slate-500 bg-slate-800/40 border-slate-800'
            : (typeof resolvedSatisfiedVal === 'boolean'
              ? (resolvedSatisfiedVal
                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                : 'text-rose-400 bg-rose-500/10 border-rose-500/20')
              : 'text-sky-400 bg-sky-500/10 border-sky-500/20');

          return (
            <div key={c.id} className="bg-slate-900/40 p-4 rounded-xl border border-slate-800 hover:border-slate-700 transition-all flex flex-col space-y-4 shadow-inner">
              <div className="flex justify-between items-start gap-2">
                <div className="flex flex-col space-y-1">
                  <span className="text-xs font-bold text-slate-200 line-clamp-1">{c.description || c.id}</span>
                  <span className="text-2xs text-slate-500 font-semibold font-mono tracking-wider uppercase">{c.type || 'boolean'}</span>
                </div>
                <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded-lg border ${percentBadgeColor}`}>
                  {currentImportance}%
                </span>
              </div>

              <div className="flex items-center gap-2 pt-2 border-t border-slate-900/30">
                <span className="text-2xs text-slate-500 font-bold uppercase tracking-wider">{t('tuner.target')}</span>
                {typeof resolvedSatisfiedVal === 'boolean' ? (
                  <Button
                    type="button"
                    variant="badge"
                    size="xs"
                    onClick={() => handleToggleSatisfiedIf(c.id)}
                    className={`font-extrabold px-2.5 py-1.5 border transition-all active:scale-95 cursor-pointer ${
                      resolvedSatisfiedVal
                        ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/25'
                        : 'bg-rose-500/10 text-rose-400 border-rose-500/20 hover:bg-rose-500/25'
                    }`}
                  >
                    {resolvedSatisfiedVal ? t('tuner.positiveTrue') : t('tuner.negativeFalse')}
                  </Button>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <input
                      type="number"
                      value={typeof resolvedSatisfiedVal === 'number' ? resolvedSatisfiedVal : 1}
                      onChange={(e) => {
                        const val = e.target.value === '' ? '' : Number(e.target.value);
                        handleUpdateSatisfiedIfValue(c.id, val);
                      }}
                      className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-2xs font-bold text-slate-200 font-mono w-16 text-center focus:outline-none focus:border-emerald-500"
                    />
                    <span className="text-2xs text-slate-500 font-bold uppercase">{t('tuner.ideal')}</span>
                  </div>
                )}
              </div>

              <div className="flex flex-col space-y-1.5 pt-1">
                <div className="flex justify-between text-2xs text-slate-500 font-semibold font-sans px-0.5">
                  <span>{t('tuner.lowImportance')}</span>
                  <span>{t('tuner.criticalImportance')}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={currentImportance}
                  onChange={(e) => handleUpdateWeight(c.id, parseInt(e.target.value))}
                  className="w-full accent-emerald-500 bg-slate-950 h-1.5 rounded-lg appearance-none cursor-pointer border border-slate-800 focus:outline-none"
                  style={{
                    background: `linear-gradient(to right, rgb(16, 185, 129) 0%, rgb(16, 185, 129) ${currentImportance}%, rgb(15, 23, 42) ${currentImportance}%, rgb(15, 23, 42) 100%)`
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
