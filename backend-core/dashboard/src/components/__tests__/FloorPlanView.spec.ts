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

const get = vi.fn()
vi.mock('src/services/api', () => ({ apiClient: { client: { get: (...args: unknown[]) => get(...args) } } }))

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
})
