import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { Quasar } from 'quasar'
import PlantsView from '../PlantsView.vue'

const get = vi.fn()
const post = vi.fn()
const del = vi.fn()

vi.mock('src/services/api', () => ({
  apiClient: {
    client: {
      defaults: { baseURL: 'http://host:8000/api/v1' },
      get: (...args: unknown[]) => get(...args),
      post: (...args: unknown[]) => post(...args),
      delete: (...args: unknown[]) => del(...args)
    }
  }
}))

// GET /plants/models: one finished plant, the provider ready.
const rose = {
  id: 1, name: 'Coral rose', description: null, source: 'photo', provider: 'replicate', status: 'ready',
  error: null, height_ft: 4, aspect: 1, triangles: 12000,
  image_url: '/plant_models/1/source.jpg', model_url: '/plant_models/1/model-1.glb', created_at: null
}
const library = (models: unknown[], ready = true) => ({
  data: { models, provider: 'replicate', provider_ready: ready, provider_problem: ready ? null : 'REPLICATE_API_TOKEN is not set' }
})

// QPage only renders inside a QLayout, so it is stubbed down to its content.
const mountView = () => mount(PlantsView, {
  global: { plugins: [Quasar], stubs: { QPage: { template: '<div><slot /></div>' } } }
})

describe('PlantsView', () => {
  beforeEach(() => {
    get.mockReset(); post.mockReset(); del.mockReset()
  })

  it('lists the library with pictures and model links from the backend origin', async () => {
    get.mockResolvedValue(library([rose]))
    const wrapper = mountView()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/plants/models')
    expect(wrapper.text()).toContain('Coral rose')
    expect(wrapper.text()).toContain('Ready')
    expect(wrapper.html()).toContain('http://host:8000/plant_models/1/model-1.glb')
  })

  it('says why models cannot be made', async () => {
    get.mockResolvedValue(library([], false))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('REPLICATE_API_TOKEN is not set')
    expect(wrapper.text()).toContain('No plants yet')
  })

  it('adds a plant from a description as a form upload', async () => {
    get.mockResolvedValue(library([]))
    post.mockResolvedValue({ data: { ...rose, id: 2, status: 'pending' } })
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.form.name = ' Lilac '
    vm.form.description = 'a purple lilac bush'
    vm.form.height = 8
    await vm.addPlant()
    expect(post).toHaveBeenCalledTimes(1)
    const [url, body] = post.mock.calls[0]
    expect(url).toBe('/plants/models')
    expect(body.get('name')).toBe('Lilac')
    expect(body.get('description')).toBe('a purple lilac bush')
    expect(body.get('height_ft')).toBe('8')
    expect(body.get('photo')).toBeNull()
    expect(vm.form.name).toBe('')
  })

  it('needs a photo or a description', async () => {
    get.mockResolvedValue(library([]))
    const wrapper = mountView()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.form.name = 'Lilac'
    await vm.addPlant()
    expect(post).not.toHaveBeenCalled()
  })

  it('deletes a plant', async () => {
    get.mockResolvedValue(library([rose]))
    del.mockResolvedValue({ data: { deleted: 1 } })
    const wrapper = mountView()
    await flushPromises()
    await (wrapper.vm as any).remove(rose)
    await flushPromises()
    expect(del).toHaveBeenCalledWith('/plants/models/1')
    expect(wrapper.findAll('.plant-card')).toHaveLength(0)
  })
})
