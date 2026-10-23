<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" @show="fill">
    <q-card class="app-card" style="width: 680px; max-width: 96vw">
      <q-card-section class="row items-center no-wrap q-pb-none">
        <div class="text-h6 text-weight-bold col">{{ client ? 'Edit client' : 'New client' }}</div>
        <q-btn flat round dense icon="close" v-close-popup />
      </q-card-section>

      <q-form @submit.prevent="save">
        <q-card-section class="q-pt-sm">
          <div class="form-section">Contact</div>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-sm-6"><q-input v-model="form.name" outlined dense label="Name *" :rules="[v => !!(v && v.trim()) || 'Required']" hide-bottom-space /></div>
            <div class="col-12 col-sm-6"><q-input v-model="form.company" outlined dense label="Company" /></div>
            <div class="col-12 col-sm-6"><q-input v-model="form.email" outlined dense type="email" label="Email" /></div>
            <div class="col-12 col-sm-6"><q-input v-model="form.phone" outlined dense label="Phone" /></div>
          </div>

          <div class="form-section">Opportunity</div>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-sm-6">
              <q-select v-model="form.stage" outlined dense emit-value map-options :options="stageOptions" label="Stage" />
            </div>
            <div class="col-6 col-sm-3">
              <q-select v-model="form.tier" outlined dense emit-value map-options :options="TIER_OPTIONS" label="Tier" />
            </div>
            <div class="col-6 col-sm-3"><q-input v-model="form.source" outlined dense label="Source" placeholder="Referral" /></div>
            <div class="col-6"><q-input v-model.number="form.deal_value" outlined dense type="number" min="0" prefix="$" label="Deal value" /></div>
            <div class="col-6">
              <q-input v-model.number="form.win_probability" outlined dense type="number" min="0" max="100" suffix="%" label="Win probability" :hint="client ? undefined : 'Blank: the stage\'s usual'" />
            </div>
          </div>

          <div class="form-section">What they want</div>
          <div class="row q-col-gutter-sm">
            <div class="col-12"><q-input v-model="form.site_address" outlined dense label="Site address" /></div>
            <div class="col-12 col-sm-6"><q-input v-model="form.preferred_style" outlined dense label="Style" placeholder="Modern farmhouse" /></div>
            <div class="col-6 col-sm-3"><q-input v-model.number="form.target_square_feet" outlined dense type="number" min="0" suffix="sq ft" label="Size" /></div>
            <div class="col-6 col-sm-3"><q-input v-model.number="form.target_budget" outlined dense type="number" min="0" prefix="$" label="Budget" /></div>
            <div class="col-12 col-sm-6"><q-input v-model="form.target_completion_date" outlined dense type="date" stack-label label="Move-in target" /></div>
            <div class="col-12 col-sm-6">
              <q-select
                v-model="form.tags"
                outlined
                dense
                multiple
                use-chips
                use-input
                new-value-mode="add-unique"
                hide-dropdown-icon
                label="Tags"
                input-debounce="0"
              />
            </div>
            <div class="col-12"><q-input v-model="form.requirements" outlined dense autogrow label="Requirements & notes from discovery" /></div>
          </div>

          <div class="form-section">Next step</div>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-sm-5"><q-input v-model="form.follow_up" outlined dense type="date" stack-label label="Follow up on" /></div>
            <div class="col-12 col-sm-7"><q-input v-model="form.next_action" outlined dense label="Next action" placeholder="Send the proposal" /></div>
          </div>
        </q-card-section>

        <q-card-section v-if="error" class="q-pt-none">
          <q-banner rounded dense class="banner-error">{{ error }}</q-banner>
        </q-card-section>
        <q-card-actions align="right" class="q-px-md q-pb-md">
          <q-btn flat no-caps label="Cancel" v-close-popup />
          <q-btn unelevated no-caps color="primary" type="submit" :label="client ? 'Save' : 'Add client'" :loading="saving" />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useCrmStore, PIPELINE_STAGES, TIER_OPTIONS } from 'src/stores/crm'
import type { Client, ClientDraft, ClientTier, LeadStage } from 'src/types/crm'
import { errorMessage } from 'src/utils/errors'

const props = defineProps<{ modelValue: boolean; client?: Client | null }>()
const emit = defineEmits<{ (e: 'update:modelValue', open: boolean): void; (e: 'saved', client: Client): void }>()

const $q = useQuasar()
const crm = useCrmStore()
const saving = ref(false)
const error = ref<string | null>(null)
const stageOptions = PIPELINE_STAGES.map(s => ({ value: s.id, label: s.label }))

const blank = () => ({
  name: '', company: '', email: '', phone: '',
  stage: 'new_inquiry' as LeadStage, tier: 'standard' as ClientTier, source: '',
  deal_value: null as number | null, win_probability: null as number | null,
  site_address: '', preferred_style: '', target_square_feet: null as number | null, target_budget: null as number | null,
  target_completion_date: '', tags: [] as string[], requirements: '', follow_up: '', next_action: ''
})
const form = reactive(blank())

const fill = () => {
  error.value = null
  const c = props.client
  Object.assign(form, blank())
  if (!c) return
  Object.assign(form, {
    name: c.name, company: c.company ?? '', email: c.email ?? '', phone: c.phone ?? '',
    stage: c.stage, tier: c.tier, source: c.source ?? '',
    deal_value: c.deal_value || null, win_probability: c.win_probability,
    site_address: c.site_address ?? '', preferred_style: c.preferred_style ?? '',
    target_square_feet: c.target_square_feet, target_budget: c.target_budget,
    target_completion_date: c.target_completion_date ?? '', tags: [...(c.tags ?? [])],
    requirements: c.requirements ?? '', follow_up: c.next_follow_up_at?.slice(0, 10) ?? '', next_action: c.next_action ?? ''
  })
}

const text = (v: string) => v.trim() || null

const save = async () => {
  saving.value = true
  error.value = null
  const fields: ClientDraft & { name: string } = {
    name: form.name.trim(),
    company: text(form.company), email: text(form.email), phone: text(form.phone),
    tier: form.tier, source: text(form.source),
    deal_value: form.deal_value || 0,
    site_address: text(form.site_address), preferred_style: text(form.preferred_style),
    target_square_feet: form.target_square_feet || null, target_budget: form.target_budget || null,
    target_completion_date: form.target_completion_date || null,
    tags: form.tags, requirements: text(form.requirements),
    next_follow_up_at: form.follow_up ? `${form.follow_up}T09:00:00` : null,
    next_action: text(form.next_action)
  }
  // Leave the probability out to get the stage's usual one (a stage change resets it too).
  const stageChanged = !props.client || props.client.stage !== form.stage
  if (form.win_probability !== null && !(stageChanged && props.client && form.win_probability === props.client.win_probability)) {
    fields.win_probability = form.win_probability
  }
  if (stageChanged) fields.stage = form.stage
  try {
    const saved = props.client ? await crm.update(props.client.id, fields) : await crm.create(fields)
    $q.notify({ type: 'positive', message: props.client ? 'Client saved' : `Added ${saved.name}` })
    emit('saved', saved)
    emit('update:modelValue', false)
  } catch (err) {
    error.value = errorMessage(err, 'Could not save the client')
  } finally {
    saving.value = false
  }
}
</script>

<style lang="sass" scoped>
.form-section
  font-size: 0.72rem
  font-weight: 700
  letter-spacing: 0.06em
  text-transform: uppercase
  color: var(--app-muted)
  margin: 14px 0 6px
  &:first-child
    margin-top: 0
</style>
