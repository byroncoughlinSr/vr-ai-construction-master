import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type {
  ActivityKind, Client, ClientDraft, ClientSentiment, EmailPurpose, LeadStage, Pipeline, PipelineStageConfig
} from 'src/types/crm'

// Display settings per stage; ids and labels follow crm_service.STAGES.
export const PIPELINE_STAGES: PipelineStageConfig[] = [
  { id: 'new_inquiry', label: 'New inquiry', color: 'indigo', icon: 'mail_outline', description: 'First contact and site questions' },
  { id: 'vr_consultation', label: 'VR consultation', color: 'teal', icon: 'view_in_ar', description: 'Walking a first layout in the headset' },
  { id: 'schematic_design', label: 'Floor plan design', color: 'blue', icon: 'architecture', description: 'Refining rooms, doors and the outside' },
  { id: 'cost_estimation', label: 'Estimate & proposal', color: 'amber-9', icon: 'calculate', description: 'Pricing the plan and sending the proposal' },
  { id: 'contract_permitting', label: 'Contract & permits', color: 'purple', icon: 'gavel', description: 'Signing and filing for permits' },
  { id: 'active_build', label: 'Under construction', color: 'positive', icon: 'foundation', description: 'On site: schedule, inspections, draws' },
  { id: 'handover', label: 'Handover', color: 'cyan-8', icon: 'key', description: 'Final walkthrough and warranty' },
  { id: 'closed_lost', label: 'Lost', color: 'grey-7', icon: 'block', description: 'Not going ahead' }
]

export const OPEN_STAGES: LeadStage[] = ['new_inquiry', 'vr_consultation', 'schematic_design', 'cost_estimation', 'contract_permitting']

export const stageConfig = (stage: LeadStage): PipelineStageConfig =>
  PIPELINE_STAGES.find(s => s.id === stage) ?? PIPELINE_STAGES[0]

export const ACTIVITY_KINDS: Array<{ value: ActivityKind; label: string; icon: string }> = [
  { value: 'call', label: 'Call', icon: 'call' },
  { value: 'email', label: 'Email', icon: 'mail' },
  { value: 'meeting', label: 'Meeting', icon: 'groups' },
  { value: 'vr_demo', label: 'VR demo', icon: 'view_in_ar' },
  { value: 'site_visit', label: 'Site visit', icon: 'place' },
  { value: 'note', label: 'Note', icon: 'sticky_note_2' }
]

export const activityIcon = (kind: ActivityKind): string =>
  ({ stage_change: 'swap_horiz', ai: 'auto_awesome' } as Record<string, string>)[kind] ??
  ACTIVITY_KINDS.find(k => k.value === kind)?.icon ?? 'event_note'

export const SENTIMENT_COLORS: Record<ClientSentiment, string> = {
  enthusiastic: 'positive',
  positive: 'teal',
  neutral: 'blue-grey',
  concerned: 'warning'
}

export const TIER_OPTIONS = [
  { value: 'standard', label: 'Standard' },
  { value: 'premium', label: 'Premium' },
  { value: 'vip', label: 'VIP' },
  { value: 'commercial', label: 'Commercial' }
]

export interface ActivityFields {
  kind: ActivityKind
  summary: string
  details?: string | null
  sentiment?: ClientSentiment | null
  action_items?: string[]
  author?: string | null
  occurred_at?: string | null
}

/** Clients and the pipeline, from /api/v1/crm. The list holds every client;
 * `selected` is the full record (with activities) of the one opened. */
export const useCrmStore = defineStore('crm', {
  state: () => ({
    clients: [] as Client[],
    pipeline: null as Pipeline | null,
    selected: null as Client | null,
    loading: false,
    loaded: false,
    error: null as string | null,
    filterStage: 'all' as LeadStage | 'all' | 'open',
    searchQuery: ''
  }),

  getters: {
    filteredClients: (state): Client[] => {
      const query = state.searchQuery.toLowerCase().trim()
      return state.clients.filter(c => {
        const stageOk =
          state.filterStage === 'all' ? c.stage !== 'closed_lost'
            : state.filterStage === 'open' ? OPEN_STAGES.includes(c.stage)
              : c.stage === state.filterStage
        const text = [c.name, c.email, c.company, c.site_address, c.preferred_style, ...(c.tags ?? [])]
          .filter(Boolean).join(' ').toLowerCase()
        return stageOk && (!query || text.includes(query))
      })
    },
    clientsForProject: state => (projectId: number | null) =>
      projectId ? state.clients.filter(c => c.project_id === projectId) : [],
    followUpsDue: (state): number => state.pipeline?.follow_ups_due.length ?? 0
  },

  actions: {
    _put(client: Client) {
      const summary = { ...client }
      delete summary.activities
      const index = this.clients.findIndex(c => c.id === client.id)
      if (index === -1) this.clients.unshift(summary)
      else this.clients[index] = summary
      if (client.activities && this.selected?.id === client.id) this.selected = client
    },

    async load() {
      this.loading = true
      this.error = null
      try {
        const [list, pipeline] = await Promise.all([
          apiClient.get<{ clients: Client[] }>('/crm/clients'),
          apiClient.get<Pipeline>('/crm/pipeline')
        ])
        this.clients = list.clients
        this.pipeline = pipeline
        this.loaded = true
      } catch (err) {
        this.error = (err as Error).message
        throw err
      } finally {
        this.loading = false
      }
    },

    async refreshPipeline() {
      this.pipeline = await apiClient.get<Pipeline>('/crm/pipeline')
    },

    async open(clientId: number): Promise<Client> {
      const client = await apiClient.get<Client>(`/crm/clients/${clientId}`)
      this.selected = client
      this._put(client)
      return client
    },

    close() {
      this.selected = null
    },

    async create(fields: ClientDraft & { name: string }): Promise<Client> {
      const client = await apiClient.post<Client>('/crm/clients', fields)
      this.selected = client
      this._put(client)
      await this.refreshPipeline()
      return client
    },

    async update(clientId: number, fields: ClientDraft): Promise<Client> {
      const client = await apiClient.patch<Client>(`/crm/clients/${clientId}`, fields)
      this._put(client)
      await this.refreshPipeline()
      return client
    },

    moveStage(clientId: number, stage: LeadStage) {
      return this.update(clientId, { stage })
    },

    async remove(clientId: number) {
      await apiClient.delete(`/crm/clients/${clientId}`)
      this.clients = this.clients.filter(c => c.id !== clientId)
      if (this.selected?.id === clientId) this.selected = null
      await this.refreshPipeline()
    },

    async logActivity(clientId: number, fields: ActivityFields): Promise<Client> {
      const client = await apiClient.post<Client>(`/crm/clients/${clientId}/activities`, fields)
      this._put(client)
      await this.refreshPipeline()
      return client
    },

    async deleteActivity(clientId: number, activityId: number) {
      const client = await apiClient.delete<Client>(`/crm/clients/${clientId}/activities/${activityId}`)
      this._put(client)
    },

    /** Start a project for the client (or link `projectId`). Returns the project id. */
    async startProject(clientId: number, options: { name?: string; project_id?: number } = {}): Promise<number> {
      const result = await apiClient.post<{ project_id: number; client: Client }>(
        `/crm/clients/${clientId}/project`, options
      )
      this._put(result.client)
      return result.project_id
    },

    async generateInsights(clientId: number): Promise<Client> {
      const result = await apiClient.post<{ client: Client }>(`/crm/clients/${clientId}/ai/insights`, {})
      this._put(result.client)
      return result.client
    },

    draftEmail(clientId: number, purpose: EmailPurpose, notes?: string, sender?: string) {
      return apiClient.post<{ subject: string; body: string; source: string }>(
        `/crm/clients/${clientId}/ai/draft`, { purpose, notes: notes || null, sender: sender || null }
      )
    }
  }
})
