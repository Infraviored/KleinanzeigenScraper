export interface Campaign {
  id: number
  name: string
  route_id?: number | null
}

export interface KnowledgeSet {
  id?: number
  name: string
  expert_knowledge: string
  item_json: Record<string, unknown> | string
  market_memo?: string
  good_reference_description?: string
  bad_reference_description?: string
  market_samples_json?: string
  source_search_url?: string
  sample_timestamp?: string
}

export interface SearchTarget {
  id?: number
  campaign_id: number | null
  name: string
  url: string
  enabled: boolean
  knowledge_set_id: number | null
  expert_knowledge?: string
  item_json?: Record<string, unknown> | string
}
export interface SampleListing {
  id: string
  title: string
  description: string
  details: string
}

export type FieldType = 'boolean' | 'number' | 'enum' | 'tier' | 'text';
export type MissingBehavior = 'critical_gap' | 'penalize' | 'cap_upside' | 'neutral';
export type Polarity = 'positive' | 'negative' | 'neutral';

export interface FieldDefinition {
  id: string;
  label: string;
  description?: string;
  type: FieldType;
  unit?: string;
  values?: string[];
  importance: 'high' | 'medium' | 'low';
  buyer_wants?: Record<string, unknown>;
  missing_behavior?: MissingBehavior;
  polarity?: Polarity;
  extraction_hint?: string;
}

export interface ExtractedFieldValue {
  value: string | number | boolean | null;
  evidence_quote?: string;
  reasoning?: string;
  confidence?: 'high' | 'medium' | 'low';
}

export interface Listing {
  id: string
  title: string
  price: string
  location: string
  url: string
  short_description: string
  detailed_description: string
  extracted_facts: Record<string, unknown>
  niceness_score?: number | null
  status: string
  search_id: number
  item_name?: string
  campaign_name?: string
  llm_processed: boolean
  llm_processed_time?: string
  last_description_changed_at?: string
  last_ai_evaluated_at?: string
  details?: Record<string, string>
  images?: string[]
  year?: string
  mileage?: string
  cubic_capacity?: string
  date_string?: string
  summary?: string
  criteria_evaluations?: {
    id?: string
    name: string
    reasoning: string
    status: 'satisfied' | 'neutral' | 'violated' | 'Needs Re-Evaluation'
    value?: unknown
  }[]
  field_evaluations?: {
    field: FieldDefinition
    extracted: ExtractedFieldValue
    status: 'satisfied' | 'partial' | 'violated' | 'missing' | 'missing_critical'
  }[]
  highlights?: {
    label: string
    type: 'maintenance' | 'warning' | 'feature'
    sentiment: 'positive' | 'negative' | 'neutral'
    evidence_quote: string
    confidence: 'high' | 'med' | 'low'
  }[]
  special_info?: string[]
  draft_message?: string
  description?: string
  dimensions?: Record<string, { score: number; reasoning: string }>
  reference_comparison?: { closer_to: 'good' | 'bad' | 'mixed'; reasoning: string }
}

export interface ScraperProgressCardProps {
  isScraping: boolean;
  scrapingStatus: string;
  scrapingProgress: {
    phase: string;
    current: number;
    total: number;
    status: string;
  } | null;
  liveLogs: string;
  showLogConsole: boolean;
  setShowLogConsole: (val: boolean) => void;
}

export interface ParsedKnowledgeConfig {
  product_domain?: string;
  dimensions_enabled?: boolean;
  dimensions_weight?: number;
  fields?: FieldDefinition[];
  extraction_criteria?: {
    id: string;
    description?: string;
    type?: string;
    question?: string;
  }[];
  scoring_model?: {
    weights?: Record<string, {
      satisfied_if?: unknown;
      importance?: number;
    }>;
  };
}

