import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { Quasar } from 'quasar'
import ModelLibraryView from '../ModelLibraryView.vue'

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
const mountView = (kind: 'plant' | 'furniture' = 'plant') => mount(ModelLibraryView, {
  props: { kind },
  global: { plugins: [Quasar], stubs: { QPage: { template: '<div><slot /></div>' } } }
})

describe('ModelLibraryView', () => {
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
    await vm.addModel()
    expect(post).toHaveBeenCalledTimes(1)
    const [url, body, config] = post.mock.calls[0]
    expect(url).toBe('/plants/models')
    expect(config.headers['Content-Type']).toBe('multipart/form-data')
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
    await vm.addModel()
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

  it('serves the furniture library from its own endpoint', async () => {
    const chair = { ...rose, id: 3, kind: 'furniture', name: "Grandma's armchair", model_url: null, status: 'generating' }
    get.mockResolvedValue(library([chair]))
    post.mockResolvedValue({ data: { ...chair, id: 4 } })
    const wrapper = mountView('furniture')
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/furniture/models')
    expect(wrapper.text()).toContain('Furniture Library')
    expect(wrapper.text()).toContain('Making model')
    const vm = wrapper.vm as any
    vm.form.name = 'Walnut desk'
    vm.form.description = 'a mid-century walnut desk'
    await vm.addModel()
    expect(post.mock.calls[0][0]).toBe('/furniture/models')
    await vm.remove(chair)
    expect(del).toHaveBeenCalledWith('/furniture/models/3')
    wrapper.unmount()
  })
  it('recolours a model with one of its own colours and can reset it', async () => {
    const island = { ...rose, id: 2, kind: 'furniture', name: 'Kitchen island' }
    get.mockImplementation((url: string) => Promise.resolve(
      url.endsWith('/colors')
        ? { data: { colors: [{ color: '#b49b78', share: 0.4 }, { color: '#222222', share: 0.3 }] } }
        : library([island])
    ))
    post.mockResolvedValueOnce({ data: { ...island, recolored: true, model_url: '/plant_models/2/model-2.glb', changed: 0.38 } })
    const wrapper = mountView('furniture')
    await flushPromises()
    const vm = wrapper.vm as any
    vm.openRecolor(vm.models[0])
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/furniture/models/2/colors')
    expect(vm.recolor.colors).toHaveLength(2)
    vm.recolor.from = '#b49b78'
    vm.recolor.to = '#f4f4f0'
    await vm.applyRecolor()
    expect(post).toHaveBeenCalledWith('/furniture/models/2/recolor', { from_color: '#b49b78', to_color: '#f4f4f0', tolerance: 0.5 })
    expect(vm.models[0].recolored).toBe(true)
    expect(vm.recolor.message).toContain('38%')

    post.mockResolvedValueOnce({ data: { ...island, recolored: false } })
    await vm.resetColors()
    expect(post).toHaveBeenLastCalledWith('/furniture/models/2/reset-colors')
    expect(vm.models[0].recolored).toBe(false)
    wrapper.unmount()
  })
})
