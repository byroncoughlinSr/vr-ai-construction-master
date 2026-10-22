// Client CRM shapes, as returned by /api/v1/crm (app/services/crm_service.py).

export type LeadStage =
  | 'new_inquiry'
  | 'vr_consultation'
  | 'schematic_design'
  | 'cost_estimation'
  | 'contract_permitting'
  | 'active_build'
  | 'handover'
  | 'closed_lost'

export type ClientTier = 'standard' | 'premium' | 'vip' | 'commercial'

export type ClientSentiment = 'enthusiastic' | 'positive' | 'neutral' | 'concerned'

export type ActivityKind =
  | 'note'
  | 'call'
  | 'email'
  | 'meeting'
  | 'vr_demo'
  | 'site_visit'
  | 'stage_change'
  | 'ai'

export interface ClientActivity {
  id: number
  client_id: number
  kind: ActivityKind
  summary: string
  details: string | null
  sentiment: ClientSentiment | null
  action_items: string[]
  author: string | null
  occurred_at: string | null
}

export interface ClientInsights {
  preferences: string[]
  risks: string[]
  next_best_action: string | null
}

export interface Client {
  id: number
  name: string
  email: string | null
  phone: string | null
  company: string | null
  stage: LeadStage
  stage_label: string
  tier: ClientTier
  source: string | null
  deal_value: number
  win_probability: number
  lost_reason: string | null
  site_address: string | null
  preferred_style: string | null
  target_budget: number | null
  target_square_feet: number | null
  target_completion_date: string | null
  requirements: string | null
  tags: string[]
  next_follow_up_at: string | null
  next_action: string | null
  last_contact_at: string | null
  sentiment: ClientSentiment | null
  ai_summary: string | null
  ai_insights: ClientInsights | null
  ai_updated_at: string | null
  project_id: number | null
  project_name: string | null
  activity_count: number
  created_at: string | null
  updated_at: string | null
  activities?: ClientActivity[]
}

// What the client form edits (create and update).
export type ClientDraft = Partial<
  Pick<
    Client,
    | 'name' | 'email' | 'phone' | 'company' | 'stage' | 'tier' | 'source' | 'deal_value'
    | 'win_probability' | 'site_address' | 'preferred_style' | 'target_budget'
    | 'target_square_feet' | 'target_completion_date' | 'requirements' | 'tags'
    | 'next_follow_up_at' | 'next_action' | 'sentiment' | 'lost_reason' | 'project_id'
  >
>

export interface PipelineStage {
  id: LeadStage
  label: string
  count: number
  value: number
}

export interface Pipeline {
  stages: PipelineStage[]
  open_count: number
  open_value: number
  weighted_value: number
  won_value: number
  win_rate: number | null
  follow_ups_due: Array<{ id: number; name: string; next_follow_up_at: string; next_action: string | null }>
  stale: Array<{ id: number; name: string; last_contact_at: string | null }>
}

export interface PipelineStageConfig {
  id: LeadStage
  label: string
  color: string
  icon: string
  description: string
}

export type EmailPurpose = 'follow_up' | 'vr_invite' | 'progress_update' | 'change_order' | 'proposal' | 'custom'
