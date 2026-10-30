import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { Quasar } from 'quasar'
import KitchenStyles from '../KitchenStyles.vue'

const get = vi.fn()
const post = vi.fn()
const put = vi.fn()
const del = vi.fn()

vi.mock('src/services/api', () => ({
  apiClient: {
    client: {
      get: (...args: unknown[]) => get(...args),
      post: (...args: unknown[]) => post(...args),
      put: (...args: unknown[]) => put(...args),
      delete: (...args: unknown[]) => del(...args)
    }
  }
}))

const defaults = {
  cabinet: '#f2f1ec', door: 'flat', uppers: 'solid', handle: '#c3c6c9', crown: false, top: '#e6e1d8', fleck: null,
  backsplash: 'none', backsplash_color: '#d9d6cf', stove_model_id: null, fridge_model_id: null
}
const byron = {
  ...defaults, id: 1, name: "Byron's kitchen", cabinet: '#ece4d4', door: 'raised', uppers: 'glass', crown: true,
  top: '#1b1b1d', fleck: '#8f8a80', backsplash: 'mosaic', backsplash_color: '#4a5058', stove_model_id: 7, created_at: null
}
const models = [{ id: 7, name: 'Stove and microwave', status: 'ready' }, { id: 8, name: 'Fridge', status: 'generating' }]
const mountIt = () => mount(KitchenStyles, { props: { models }, global: { plugins: [Quasar] } })

describe('KitchenStyles', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); put.mockReset(); del.mockReset() })

  it('lists the styles with their appliances', async () => {
    get.mockResolvedValue({ data: { styles: [byron], defaults } })
    const wrapper = mountIt()
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/kitchen-styles')
    expect(wrapper.text()).toContain("Byron's kitchen")
    expect(wrapper.text()).toContain('Raised panel doors · glass uppers · mosaic backsplash · crown · Stove and microwave')
    wrapper.unmount()
  })

  it('makes a new style from the defaults and edits one', async () => {
    get.mockResolvedValue({ data: { styles: [byron], defaults } })
    post.mockResolvedValue({ data: {} })
    put.mockResolvedValue({ data: {} })
    const wrapper = mountIt()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.openEditor()
    vm.editor.name = ' Beach house '
    vm.editor.style.door = 'shaker'
    await vm.save()
    expect(post).toHaveBeenCalledWith('/kitchen-styles', { name: 'Beach house', style: { ...defaults, door: 'shaker' } })

    vm.openEditor(byron)
    expect(vm.editor.style).not.toHaveProperty('created_at')
    vm.editor.style.fridge_model_id = 8
    await vm.save()
    expect(put).toHaveBeenCalledWith('/kitchen-styles/1', expect.objectContaining({ name: "Byron's kitchen" }))
    expect(put.mock.calls[0][1].style.fridge_model_id).toBe(8)
    wrapper.unmount()
  })
})
