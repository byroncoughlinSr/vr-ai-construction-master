import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { usePunchListStore } from '../punchList'
import type { PunchItem } from 'src/types/controls'

const item = (id: number, fields: Partial<PunchItem>): PunchItem => ({
  id, project_id: 1, number: id, code: `PL-00${id}`, title: `Item ${id}`, description: null, room: null,
  trade: 'general', priority: 'medium', status: 'open', assignee: null, due_date: null, phase_id: null,
  phase_name: null, overdue: false, closed_at: null, created_at: null,
  ...fields
})

describe('punch list store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('filters by status group, room, trade and text', () => {
    const punch = usePunchListStore()
    punch.items = [
      item(1, { room: 'Kitchen', trade: 'paint', assignee: 'Dana' }),
      item(2, { room: 'Kitchen', trade: 'tile', status: 'ready' }),
      item(3, { status: 'closed' })
    ]
    expect(punch.filteredItems.map(i => i.id)).toEqual([1, 2]) // "active" hides closed
    punch.filterStatus = 'closed'
    expect(punch.filteredItems.map(i => i.id)).toEqual([3])
    punch.filterStatus = 'all'
    punch.filterRoom = 'Unassigned'
    expect(punch.filteredItems.map(i => i.id)).toEqual([3])
    punch.filterRoom = 'Kitchen'
    punch.filterTrade = 'tile'
    expect(punch.filteredItems.map(i => i.id)).toEqual([2])
    punch.filterTrade = null
    punch.searchQuery = 'dana'
    expect(punch.filteredItems.map(i => i.id)).toEqual([1])
  })

  it('offers the floor plan rooms first, then other locations in use', () => {
    const punch = usePunchListStore()
    punch.rooms = ['Kitchen', 'Office']
    punch.items = [item(1, { room: 'Exterior' }), item(2, { room: 'Kitchen' }), item(3, { room: 'Exterior' })]
    expect(punch.roomOptions).toEqual(['Kitchen', 'Office', 'Exterior'])
  })
})
