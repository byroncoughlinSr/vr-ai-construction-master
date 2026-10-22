import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCrmStore } from '../crm'
import type { Client } from 'src/types/crm'

const client = (id: number, fields: Partial<Client>): Client => ({
  id, name: `Client ${id}`, email: null, phone: null, company: null, stage: 'new_inquiry', stage_label: '', tier: 'standard',
  source: null, deal_value: 0, win_probability: 10, lost_reason: null, site_address: null, preferred_style: null,
  target_budget: null, target_square_feet: null, target_completion_date: null, requirements: null, tags: [],
  next_follow_up_at: null, next_action: null, last_contact_at: null, sentiment: null, ai_summary: null, ai_insights: null,
  ai_updated_at: null, project_id: null, project_name: null, activity_count: 0, created_at: null, updated_at: null,
  ...fields
})

describe('crm store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('filters by stage group and text', () => {
    const crm = useCrmStore()
    crm.clients = [
      client(1, { stage: 'new_inquiry', site_address: '12 Oak Lane' }),
      client(2, { stage: 'active_build', tags: ['ski estate'] }),
      client(3, { stage: 'closed_lost' })
    ]
    expect(crm.filteredClients.map(c => c.id)).toEqual([1, 2]) // "all active" hides lost
    crm.filterStage = 'open'
    expect(crm.filteredClients.map(c => c.id)).toEqual([1])
    crm.filterStage = 'closed_lost'
    expect(crm.filteredClients.map(c => c.id)).toEqual([3])
    crm.filterStage = 'all'
    crm.searchQuery = 'SKI'
    expect(crm.filteredClients.map(c => c.id)).toEqual([2])
    crm.searchQuery = 'oak'
    expect(crm.filteredClients.map(c => c.id)).toEqual([1])
  })

  it('keeps activities out of the list but updates the open client', () => {
    const crm = useCrmStore()
    crm.selected = client(1, { activities: [] })
    crm._put(client(1, { name: 'Renamed', activities: [] }))
    expect(crm.clients[0].name).toBe('Renamed')
    expect(crm.clients[0].activities).toBeUndefined()
    expect(crm.selected?.name).toBe('Renamed')

    crm._put(client(2, { activities: [] }))
    expect(crm.selected?.id).toBe(1)
  })
})
