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
    <div className="bg-bg-surface/50 p-5 border border-border-subtle rounded-2xl mt-4 space-y-4">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-border-subtle pb-3 gap-2">
        <div>
          <h4 className="text-xl font-bold text-text-primary flex items-center gap-1.5">
            <span>{t('tuner.title')}</span>
          </h4>
          <p className="text-sm text-text-muted mt-0.5">
            {t('tuner.desc')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm bg-bg-input text-text-muted border border-border-subtle px-2.5 py-1 rounded-lg font-bold font-mono">
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
            ? 'text-text-muted bg-bg-input border-border-subtle'
            : (typeof resolvedSatisfiedVal === 'boolean'
              ? (resolvedSatisfiedVal
                ? 'text-status-good bg-status-good/10 border-status-good/20'
                : 'text-status-danger bg-status-danger/10 border-status-danger/20')
              : 'text-text-secondary bg-bg-input border-border-subtle');

          return (
            <div key={c.id} className="bg-bg-surface/80 p-4 rounded-xl border border-border-subtle hover:border-brand-accent/30 transition-all flex flex-col space-y-4 shadow-inner">
              <div className="flex justify-between items-start gap-2">
                <div className="flex flex-col space-y-1">
                  <span className="text-base font-bold text-text-primary line-clamp-1">{c.description || c.id}</span>
                  <span className="text-sm text-text-muted font-mono">{c.type || 'boolean'}</span>
                </div>
                <span className={`text-sm font-mono font-bold px-2.5 py-0.5 rounded-lg border ${percentBadgeColor}`}>
                  {currentImportance}%
                </span>
              </div>

              <div className="flex items-center gap-2 pt-2 border-t border-border-subtle">
                <span className="text-sm text-text-muted font-semibold">{t('tuner.target')}</span>
                {typeof resolvedSatisfiedVal === 'boolean' ? (
                  <Button
                    type="button"
                    variant="badge"
                    size="xs"
                    onClick={() => handleToggleSatisfiedIf(c.id)}
                    className={`font-extrabold px-2.5 py-1.5 border transition-all active:scale-95 cursor-pointer ${
                      resolvedSatisfiedVal
                        ? 'bg-status-good/10 text-status-good border-status-good/20 hover:bg-status-good/25'
                        : 'bg-status-danger/10 text-status-danger border-status-danger/20 hover:bg-status-danger/25'
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
                      className="bg-bg-input border border-border-subtle rounded-lg px-2.5 py-1 text-sm font-bold text-text-primary font-mono w-16 text-center focus:outline-none focus:border-brand-accent"
                    />
                    <span className="text-sm text-text-muted font-semibold">{t('tuner.ideal')}</span>
                  </div>
                )}
              </div>

              <div className="flex flex-col space-y-1.5 pt-1">
                <div className="flex justify-between text-sm text-text-muted font-medium px-0.5">
                  <span>{t('tuner.lowImportance')}</span>
                  <span>{t('tuner.criticalImportance')}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={currentImportance}
                  onChange={(e) => handleUpdateWeight(c.id, parseInt(e.target.value))}
                  className="w-full accent-brand-accent bg-bg-input h-2 rounded-lg appearance-none cursor-pointer border border-border-subtle focus:outline-none"
                  style={{
                    background: `linear-gradient(to right, rgb(232, 121, 103) 0%, rgb(232, 121, 103) ${currentImportance}%, rgba(0, 20, 20, 0.8) ${currentImportance}%, rgba(0, 20, 20, 0.8) 100%)`
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
