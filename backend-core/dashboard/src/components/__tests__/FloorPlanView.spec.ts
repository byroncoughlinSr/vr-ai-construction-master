import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { Quasar } from 'quasar'
import FloorPlanView from '../FloorPlanView.vue'

// Two rooms side by side, joined by a doorway, with a front door and one window —
// the shape GET /projects/{id}/generate-vr returns.
const geometry = {
  rooms: [
    { id: 1, name: 'Entry Foyer', bounds: { x0: 0, x1: 2.438, z0: 0, z1: 3.658 }, dimensions: { length: 2.438, width: 3.658, height: 2.743 }, connects_to: [2] },
    { id: 2, name: 'Living Room', bounds: { x0: 2.438, x1: 7.315, z0: 0, z1: 3.658 }, dimensions: { length: 4.877, width: 3.658, height: 2.743 }, connects_to: [1] }
  ],
  doors: [
    { id: 101, position: { x: 1.219, y: 0, z: 0 }, width: 0.914, rotation: 0, door_type: 'exterior' },
    { id: 102, position: { x: 2.438, y: 0, z: 1.829 }, width: 0.914, rotation: 90, door_type: 'interior' }
  ],
  windows: [
    { id: 201, position: { x: 4.877, y: 1.52, z: 0 }, width: 1.219, rotation: 0 }
  ]
}

// The saved plan behind it (sizes in feet), as GET /projects/{id}/floor-plan returns it.
const floorPlan = {
  id: 3,
  version: 2,
  name: 'Tiny Test House',
  layout: {
    length: 24, width: 12, entry: 'Entry Foyer', split: 'x',
    parts: [{ size: 8, room: 'Entry Foyer' }, { size: 16, room: 'Living Room' }]
  },
  rooms: [
    { name: 'Entry Foyer', connects_to: ['Living Room'] },
    { name: 'Living Room', connects_to: ['Entry Foyer'] }
  ],
  change_type: 'edited',
  change_note: null,
  image_url: null
}
const savedGeometry = { ...geometry, floor_plan: { id: 3, version: 2, name: 'Tiny Test House' } }

const get = vi.fn()
const put = vi.fn()
const post = vi.fn()
vi.mock('src/services/api', () => ({
  apiClient: {
    client: {
      defaults: { baseURL: 'http://host:8000/api/v1' },
      get: (...args: unknown[]) => get(...args),
      put: (...args: unknown[]) => put(...args),
      post: (...args: unknown[]) => post(...args)
    }
  }
}))

// A saved project: geometry plus its editable floor plan.
const savedProject = () => {
  get.mockReset()
  get.mockImplementation((url: string) => Promise.resolve(
    url.endsWith('/floor-plan')
      ? { data: JSON.parse(JSON.stringify(floorPlan)) }
      : { data: { success: true, geometry: savedGeometry } }
  ))
}

const mountPlan = () => mount(FloorPlanView, {
  props: { projectId: 7 },
  global: { plugins: [Quasar] }
})

describe('FloorPlanView', () => {
  it('draws each room, doorway and window from the VR geometry', async () => {
    get.mockResolvedValue({ data: { success: true, geometry } })
    const wrapper = mountPlan()
    await flushPromises()

    expect(get).toHaveBeenCalledWith('/projects/7/generate-vr')
    expect(wrapper.findAll('svg rect')).toHaveLength(2)
    expect(wrapper.text()).toContain('Entry Foyer')
    expect(wrapper.text()).toContain('16 × 12 ft')
    expect(wrapper.text()).toContain('▲ Entry')
    expect(wrapper.text()).toContain('1 doorways')
    expect(wrapper.text()).toContain('1 windows')
  })

  it('draws the front of the house at the bottom', async () => {
    get.mockResolvedValue({ data: { success: true, geometry } })
    const wrapper = mountPlan()
    await flushPromises()

    // A wall-along-x opening at z=0 (the street side) maps to the largest SVG y.
    const windowLine = wrapper.findAll('svg line').find(l => l.attributes('stroke') === '#4FC3F7')!
    expect(Number(windowLine.attributes('y1'))).toBeCloseTo(3.658)
  })

  it('shows an empty state when the project has no rooms', async () => {
    get.mockResolvedValue({ data: { success: true, geometry: { rooms: [], doors: [], windows: [] } } })
    const wrapper = mountPlan()
    await flushPromises()
    expect(wrapper.text()).toContain('No rooms in this project yet')
  })

  it('names the house and its version for a saved floor plan', async () => {
    savedProject()
    const wrapper = mountPlan()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/projects/7/floor-plan')
    expect(wrapper.text()).toContain('Tiny Test House')
    expect(wrapper.text()).toContain('v2')
  })

  it('renames a room everywhere and saves the edit as a new version', async () => {
    savedProject()
    put.mockResolvedValue({
      data: { floor_plan: { ...floorPlan, version: 3, name: 'Renamed House' }, geometry: savedGeometry }
    })
    const wrapper = mountPlan()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.startEditing()
    vm.draft.name = 'Renamed House'
    vm.renameRoom(vm.draft.layout.parts[0], 'Front Hall')
    await vm.saveDraft()
    await flushPromises()

    const [url, body] = put.mock.calls[0]
    expect(url).toBe('/projects/7/floor-plan')
    expect(body.name).toBe('Renamed House')
    expect(body.layout.entry).toBe('Front Hall')
    expect(body.layout.parts[0].room).toBe('Front Hall')
    expect(body.rooms.map((r: any) => r.name)).toEqual(['Front Hall', 'Living Room'])
    expect(body.rooms[1].connects_to).toEqual(['Front Hall'])
    expect(wrapper.emitted('renamed')?.[0]).toEqual(['Renamed House'])
    expect(wrapper.text()).toContain('v3')
  })

  it('removes a doorway from both rooms', async () => {
    savedProject()
    const wrapper = mountPlan()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.startEditing()
    vm.setConnections('Living Room', [])
    expect(vm.draft.rooms.map((r: any) => r.connects_to)).toEqual([[], []])
  })

  it('sends a described change to the AI', async () => {
    savedProject()
    post.mockResolvedValue({
      data: { floor_plan: { ...floorPlan, version: 3, change_type: 'refined' }, geometry: savedGeometry }
    })
    const wrapper = mountPlan()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.instruction = 'make the living room bigger'
    await vm.refine()
    await flushPromises()
    expect(post).toHaveBeenCalledWith('/projects/7/floor-plan/refine', { instruction: 'make the living room bigger' })
    expect(wrapper.text()).toContain('v3')
  })
})
