import type { Listing, SearchTarget, KnowledgeSet, ParsedKnowledgeConfig } from '../types'

export interface RawHighlight {
  label: string;
  sentiment: string;
  type: string;
  evidence_quote: string;
  confidence: string;
}

export interface ExtractedFactsSchema {
  criteria?: Record<string, unknown>;
  highlights?: RawHighlight[];
  draft_message?: string;
  dimensions?: Record<string, { score: number; reasoning: string }>;
  reference_comparison?: { closer_to: 'good' | 'bad' | 'mixed'; reasoning: string };
  [key: string]: unknown;
}

/**
 * Transforms a raw database Listing record into a fully enriched, type-safe frontend Listing object
 * by evaluating its extracted facts, scoring configurations, and legacy vs. new schemas.
 */
export function transformListing(
  l: Listing,
  searchesData: SearchTarget[],
  ksData: KnowledgeSet[]
): Listing {
  const year = l.details?.['Erstzulassung'] || '';
  const mileage = l.details?.['Kilometerstand'] || '';
  const cubic_capacity = l.details?.['Hubraum'] || '';
  const date_string = l.details?.['Erstellungsdatum'] || '';

  const description = l.detailed_description || l.short_description || '';

  // Reconstruct criteria_evaluations from extracted_facts and search target schema
  const targetSearch = searchesData.find((s) => s.id === l.search_id);
  const boundSet = targetSearch && targetSearch.knowledge_set_id
    ? ksData.find((ks) => ks.id === targetSearch.knowledge_set_id)
    : null;

  let criteria_evaluations: NonNullable<Listing['criteria_evaluations']> = [];
  let special_info: string[] = [];
  let draft_message = '';
  let summary = 'Awaiting AI matching checklist evaluation...';
  let isLegacy = false;

  if (l.llm_processed && boundSet && boundSet.item_json) {
    try {
      const itemConfig = (typeof boundSet.item_json === 'string'
        ? JSON.parse(boundSet.item_json)
        : boundSet.item_json) as ParsedKnowledgeConfig;
      const extractionCriteria = itemConfig.extraction_criteria || [];

      const rawFacts = l.extracted_facts as ExtractedFactsSchema;

      // Check if schema is legacy/older (lacks a nested 'criteria' object)
      const hasCriteriaKey = rawFacts && typeof rawFacts === 'object' && 'criteria' in rawFacts;
      isLegacy = !hasCriteriaKey;
      if (hasCriteriaKey && rawFacts.criteria && typeof rawFacts.criteria === 'object') {
        const keys = Object.keys(rawFacts.criteria);
        if (keys.length > 0) {
          const firstVal = rawFacts.criteria[keys[0]];
          if (typeof firstVal !== 'object' || firstVal === null) {
            isLegacy = true;
          }
        }
      } else if (hasCriteriaKey) {
        isLegacy = true;
      }

      if (isLegacy) {
        criteria_evaluations = extractionCriteria.map((c) => {
          return {
            id: c.id,
            name: c.question || c.description || c.id,
            reasoning: 'Older schema incompatible. Needs re-evaluation.',
            status: 'Needs Re-Evaluation',
            value: 'Needs Re-Evaluation',
          };
        });
        summary = 'Needs Re-Evaluation (Incompatible older schema)';
      } else {
        const criteriaDict = rawFacts?.criteria || {};
        draft_message = rawFacts?.draft_message || '';
        const highlightsList = rawFacts?.highlights || [];
        special_info = (highlightsList as RawHighlight[])
          .filter((h) => h.sentiment === 'negative')
          .map((h) => h.label);

        if (itemConfig.fields && Array.isArray(itemConfig.fields)) {
          const field_evaluations: NonNullable<Listing['field_evaluations']> = itemConfig.fields.map((f) => {
            const factValObj = criteriaDict[f.id] as Record<string, unknown> | undefined;
            const extractedVal = factValObj ? (factValObj.value as string | number | boolean | null) : null;
            const reasoning = factValObj ? (factValObj.reasoning as string) : undefined;
            const quote = factValObj ? (factValObj.evidence_quote as string) : undefined;

            let status: 'satisfied' | 'partial' | 'violated' | 'missing' | 'missing_critical';

            if (extractedVal === null || extractedVal === undefined || extractedVal === 'unknown') {
              status = f.missing_behavior === 'critical_gap' ? 'missing_critical' : 'missing';
            } else if (f.type === 'boolean') {
              const isYes = String(extractedVal).toLowerCase() === 'yes' || extractedVal === true;
              const target = f.buyer_wants?.match !== false;
              status = isYes === target ? 'satisfied' : 'violated';
            } else if (f.type === 'number') {
              const num = Number(extractedVal);
              const min = f.buyer_wants?.min as number | undefined;
              const max = f.buyer_wants?.max as number | undefined;
              let ok = true;
              if (min !== undefined && num < min) ok = false;
              if (max !== undefined && num > max) ok = false;
              status = ok ? 'satisfied' : 'violated';
            } else if (f.type === 'enum') {
              const pref = (f.buyer_wants?.preferred as string[]) || [];
              const strVal = String(extractedVal);
              status = pref.includes(strVal) ? 'satisfied' : 'partial';
            } else if (f.type === 'tier') {
              const tierNum = Number(extractedVal);
              const minTier = (f.buyer_wants?.min as number) || 5;
              status = tierNum >= minTier ? 'satisfied' : 'partial';
            } else {
              status = extractedVal ? 'satisfied' : 'missing';
            }

            return {
              field: f,
              extracted: {
                value: extractedVal,
                reasoning,
                evidence_quote: quote,
              },
              status,
            };
          });

          const satisfiedCount = field_evaluations.filter((e) => e.status === 'satisfied').length;
          summary = `Evaluated ${field_evaluations.length} unified fields, satisfied ${satisfiedCount}/${field_evaluations.length}. Niceness Score: ${l.niceness_score}.`;

          return {
            ...l,
            year,
            mileage,
            cubic_capacity,
            date_string,
            description,
            field_evaluations,
            special_info,
            highlights: (((l.extracted_facts as ExtractedFactsSchema)?.highlights as Listing['highlights']) || []),
            draft_message,
            summary,
            dimensions: (l.extracted_facts as ExtractedFactsSchema)?.dimensions,
            reference_comparison: (l.extracted_facts as ExtractedFactsSchema)?.reference_comparison,
          };
        }

        const weights = itemConfig.scoring_model?.weights || {};

        criteria_evaluations = extractionCriteria.map((c) => {
          const criterionVal = criteriaDict[c.id];
          const factValObj =
            typeof criterionVal === 'object' && criterionVal !== null
              ? (criterionVal as Record<string, unknown>)
              : null;
          const factVal = factValObj ? (factValObj.value as string) : 'unknown';
          const reasoning = factValObj ? (factValObj.reasoning as string) : 'Not specified in listing description.';

          const wEntry = weights[c.id];
          const satisfiedIf = wEntry?.satisfied_if;
          let status: 'satisfied' | 'neutral' | 'violated' | 'Needs Re-Evaluation' = 'neutral';

          if (factVal !== 'unknown') {
            if (satisfiedIf !== undefined) {
              const isSatisfiedBool =
                (factVal === 'yes' &&
                  (satisfiedIf === 'yes' || satisfiedIf === true || satisfiedIf === 'true')) ||
                (factVal === 'no' &&
                  (satisfiedIf === 'no' || satisfiedIf === false || satisfiedIf === 'false'));
              status = isSatisfiedBool ? 'satisfied' : 'violated';
            } else {
              if (factVal === 'yes') status = 'satisfied';
              else if (factVal === 'no') status = 'violated';
            }
          }

          return {
            id: c.id,
            name: c.question || c.description || c.id,
            reasoning: reasoning,
            status: status,
            value: factVal,
          };
        });

        // Make a nice summary
        const satisfiedCount = criteria_evaluations.filter((e) => e.status === 'satisfied').length;
        summary = `Evaluated ${criteria_evaluations.length} expert criteria, satisfied ${satisfiedCount}/${criteria_evaluations.length}. Niceness Score: ${l.niceness_score}.`;
      }

    } catch (e) {
      console.error('Error generating criteria evaluations:', e);
    }
  } else if (l.llm_processed) {
    summary = `AI processed basic listing facts. Niceness Score: ${l.niceness_score}.`;
  }

  return {
    ...l,
    year,
    mileage,
    cubic_capacity,
    date_string,
    description,
    criteria_evaluations,
    special_info,
    highlights: isLegacy ? [] : (((l.extracted_facts as ExtractedFactsSchema)?.highlights as Listing['highlights']) || []),
    draft_message,
    summary,
    dimensions: (l.extracted_facts as ExtractedFactsSchema)?.dimensions,
    reference_comparison: (l.extracted_facts as ExtractedFactsSchema)?.reference_comparison,
  };
}
