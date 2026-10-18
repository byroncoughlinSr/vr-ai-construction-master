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

  it('draws open areas as outside and fits them in the drawing', async () => {
    const lShape = {
      ...geometry,
      open_areas: [{ bounds: { x0: 7.315, x1: 10, z0: 0, z1: 3.658 } }]
    }
    get.mockResolvedValue({ data: { success: true, geometry: lShape } })
    const wrapper = mountPlan()
    await flushPromises()

    expect(wrapper.findAll('svg rect')).toHaveLength(3)
    expect(wrapper.text()).toContain('Outside')
    expect(wrapper.text()).toContain('2 rooms')
    const [x, , w] = wrapper.find('svg').attributes('viewBox')!.split(' ').map(Number)
    expect(x + w).toBeCloseTo(10 + 1.2)
  })

  it('turns a room into an open area and back', async () => {
    savedProject()
    const wrapper = mountPlan()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.startEditing()

    vm.makeOpen(vm.draft.layout.parts[0])
    expect(vm.draft.layout.parts[0]).toEqual({ size: 8, open: true })
    expect(vm.draft.rooms.map((r: any) => r.name)).toEqual(['Living Room'])
    expect(vm.draft.rooms[0].connects_to).toEqual([])
    expect(vm.draft.layout.entry).toBe('Living Room')

    vm.makeRoom(vm.draft.layout.parts[0])
    expect(vm.draft.layout.parts[0]).toEqual({ size: 8, room: 'Room 2' })
    expect(vm.draft.rooms.map((r: any) => r.name)).toEqual(['Living Room', 'Room 2'])
  })

  it('draws a bay window bump-out and its angled glass', async () => {
    const withBay = JSON.parse(JSON.stringify(geometry))
    withBay.rooms[1].bay_window = {
      outline: [{ x: 3.5, z: 0 }, { x: 4.26, z: -0.76 }, { x: 5.48, z: -0.76 }, { x: 6.24, z: 0 }]
    }
    withBay.windows.push({ id: 202, position: { x: 3.88, y: 1.3, z: -0.38 }, width: 0.84, rotation: -45, bay: true })
    get.mockResolvedValue({ data: { success: true, geometry: withBay } })
    const wrapper = mountPlan()
    await flushPromises()

    expect(wrapper.find('svg polygon').attributes('points')).toBe('3.5,3.658 4.26,4.418 5.48,4.418 6.24,3.658')
    const glass = wrapper.findAll('svg line').filter(l => l.attributes('stroke') === '#4FC3F7')
    const angled = glass[glass.length - 1]
    // -45°: runs down-right to up-left in plan, i.e. both coordinates change.
    expect(Number(angled.attributes('x1'))).not.toBeCloseTo(Number(angled.attributes('x2')))
    expect(Number(angled.attributes('y1'))).not.toBeCloseTo(Number(angled.attributes('y2')))
    // The drawing grows to fit the bump-out in front of the house.
    const [, y, , h] = wrapper.find('svg').attributes('viewBox')!.split(' ').map(Number)
    expect(y + h).toBeGreaterThan(3.658 + 0.76)
  })

  it('adds, edits and removes a bay window in the editor', async () => {
    savedProject()
    put.mockResolvedValue({ data: { floor_plan: { ...floorPlan, version: 3 }, geometry: savedGeometry } })
    const wrapper = mountPlan()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.startEditing()

    const living = vm.draft.rooms[1]
    vm.setBaySide(living, 'front')
    expect(living.bay_window).toEqual({ side: 'front', style: 'angled', width: 8, depth: 2.5 })
    living.bay_window.width = 10
    vm.setBaySide(living, 'back')
    expect(living.bay_window).toEqual({ side: 'back', style: 'angled', width: 10, depth: 2.5 })

    await vm.saveDraft()
    expect(put.mock.calls[put.mock.calls.length - 1][1].rooms[1].bay_window.side).toBe('back')

    vm.startEditing()
    vm.setBaySide(vm.draft.rooms[1], 'none')
    expect(vm.draft.rooms[1].bay_window).toBeUndefined()
  })
  it('draws the yard and sums up the outside of the house', async () => {
    const green = { r: 0.3, g: 0.5, b: 0.2 }
    get.mockResolvedValue({
      data: {
        success: true,
        geometry: {
          ...geometry,
          exterior: {
            roof: [],
            parts: [
              // The ground and wall finish are not drawn in the plan.
              { shape: 'box', center: { x: 3, y: -0.1, z: 1 }, size: { x: 30, y: 0.05, z: 30 }, yaw: 0, color: green, kind: 'ground' },
              { shape: 'box', center: { x: 3, y: 1.4, z: -0.11 }, size: { x: 2, y: 2.7, z: 0.02 }, yaw: 0, color: green, kind: 'wall' },
              // A tree out front: trunk and canopy.
              { shape: 'sphere', center: { x: 1, y: 3, z: -6 }, size: { x: 3, y: 3, z: 3 }, yaw: 0, color: green, kind: 'landscape' },
              { shape: 'box', center: { x: 1, y: 1, z: -6 }, size: { x: 0.2, y: 2, z: 0.2 }, yaw: 0, color: green, kind: 'landscape' }
            ],
            spec: {
              roof: { style: 'hip', material: 'clay_tile', color: '#b5562f' },
              walls: { material: 'stucco', color: '#e3d4b6' },
              landscape: [{ type: 'tree' }, { type: 'palm' }, { type: 'palm' }]
            }
          }
        }
      }
    })
    const wrapper = mountPlan()
    await flushPromises()

    expect(wrapper.findAll('svg ellipse')).toHaveLength(1)
    expect(wrapper.findAll('svg rect')).toHaveLength(3) // two rooms and the trunk
    // The canopy (higher) is drawn after the trunk.
    const yard = wrapper.findAll('svg g[transform]')
    expect(yard[1].find('ellipse').exists()).toBe(true)
    // The drawing reaches the tree in the front yard: 6 m in front of the house.
    const [, , , height] = (wrapper.find('svg').attributes('viewBox') ?? '').split(' ').map(Number)
    expect(height).toBeGreaterThan(3.658 + 6)
    const summary = wrapper.find('.exterior-summary').text()
    expect(summary).toContain('hip roof, clay tile')
    expect(summary).toContain('stucco walls')
    expect(summary).toContain('1 tree, 2 palms')
  })

  it('draws plants, hedges and photo models, and names the plants', async () => {
    const coral = { r: 0.97, g: 0.51, b: 0.47 }
    get.mockResolvedValue({
      data: {
        success: true,
        geometry: {
          ...geometry,
          exterior: {
            roof: [],
            parts: [],
            plant_meshes: {},
            plants: [
              { mesh: 'rose-1', position: { x: 1, y: -0.1, z: -2 }, scale: { x: 1, y: 1.2, z: 1 }, yaw: 30, color: coral, name: 'coral rose' },
              { mesh: 'bed-2', position: { x: 0, y: 0, z: 0 }, scale: { x: 1, y: 1, z: 1 }, yaw: 0, color: coral, baked: true },
              {
                mesh: 'hedge-3', position: { x: 0, y: 0, z: 0 }, scale: { x: 1, y: 1, z: 1 }, yaw: 0, color: coral, baked: true,
                line: { from: { x: -1, z: -8 }, to: { x: 6, z: -8 }, width: 0.6 }
              }
            ],
            models: [{ model_id: 4, name: 'Coral rose', url: '/plant_models/4/m.glb', position: { x: 3, y: -0.1, z: -2 }, scale: 1.2, yaw: 0, width: 0.9 }],
            spec: {
              landscape: [
                { type: 'shrub', plant: 'coral rose' }, { type: 'shrub', plant: 'coral rose' },
                { type: 'flower_bed', plant: 'tulips' }, { type: 'hedge' }
              ]
            }
          }
        }
      }
    })
    const wrapper = mountPlan()
    await flushPromises()

    const plants = wrapper.findAll('circle.plant')
    expect(plants).toHaveLength(1) // the bed's flowers are not drawn on their own
    expect(plants[0].attributes('r')).toBe('0.5')
    expect(plants[0].find('title').text()).toBe('coral rose')
    expect(wrapper.find('line.hedge').attributes('stroke-width')).toBe('0.6')
    expect(wrapper.find('circle.plant-model title').text()).toContain('Coral rose')
    // The drawing reaches the hedge 8 m in front of the house.
    const [, , , height] = (wrapper.find('svg').attributes('viewBox') ?? '').split(' ').map(Number)
    expect(height).toBeGreaterThan(3.658 + 8)
    const summary = wrapper.find('.exterior-summary').text()
    expect(summary).toContain('2 coral roses, 1 tulips, 1 hedge (1 from photos)')
  })

  it('draws a sliding glass door to the yard and notes what did not fit', async () => {
    const withPatio = JSON.parse(JSON.stringify(geometry))
    withPatio.doors.push({
      id: 103, position: { x: 4.877, y: 0, z: 3.658 }, width: 1.829, rotation: 0,
      door_type: 'patio', style: 'sliding_glass', side: 'back', rooms: [2]
    })
    withPatio.notes = ['Entry Foyer has no left outside wall for a french door']
    get.mockResolvedValue({ data: { success: true, geometry: withPatio } })
    const wrapper = mountPlan()
    await flushPromises()

    const patio = wrapper.find('g.patio-door')
    expect(patio.exists()).toBe(true)
    expect(patio.findAll('line').some(l => l.attributes('stroke') === '#4FC3F7')).toBe(true)
    expect(patio.findAll('line').filter(l => l.attributes('stroke') === '#2E7D32')).toHaveLength(2)
    // Still one doorway between rooms; the yard door is counted on its own.
    expect(wrapper.text()).toContain('1 doorways')
    expect(wrapper.text()).toContain('1 to the yard')
    expect(wrapper.text()).toContain('Entry Foyer has no left outside wall for a french door')
  })
})
