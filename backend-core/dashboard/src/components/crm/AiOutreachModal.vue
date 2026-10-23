<template>
  <q-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" @show="onShow">
    <q-card class="app-card" style="width: 680px; max-width: 96vw">
      <q-card-section class="row items-center no-wrap q-pb-none">
        <q-icon name="auto_awesome" color="primary" size="22px" class="q-mr-sm" />
        <div class="col">
          <div class="text-h6 text-weight-bold">Draft an email</div>
          <div class="text-caption text-muted">To {{ client?.name }}{{ client?.email ? ` <${client.email}>` : '' }} — written from their record and project; nothing is sent from here.</div>
        </div>
        <q-btn flat round dense icon="close" v-close-popup />
      </q-card-section>

      <q-card-section class="q-gutter-y-sm">
        <div class="row q-gutter-xs">
          <q-btn
            v-for="p in PURPOSES"
            :key="p.value"
            :outline="purpose !== p.value"
            :unelevated="purpose === p.value"
            color="primary"
            no-caps
            dense
            class="q-px-sm"
            :icon="p.icon"
            :label="p.label"
            @click="purpose = p.value"
          />
        </div>
        <q-input v-model="notes" outlined dense autogrow label="Points to include (optional)" placeholder="Mention the walkthrough is Thursday at 2pm…" />
        <div class="row items-center q-gutter-sm">
          <q-btn unelevated no-caps color="primary" icon="auto_awesome" :label="subject ? 'Redraft' : 'Draft it'" :loading="drafting" @click="draft" />
          <span v-if="source" class="text-caption text-muted">via {{ source }}</span>
        </div>
        <q-banner v-if="error" rounded dense class="banner-error">{{ error }}</q-banner>

        <template v-if="subject || body">
          <q-separator class="q-my-sm" />
          <q-input v-model="subject" outlined dense label="Subject" />
          <q-input v-model="body" outlined autogrow type="textarea" label="Message" :input-style="{ minHeight: '220px' }" />
        </template>
      </q-card-section>

      <q-card-actions v-if="subject || body" class="q-px-md q-pb-md">
        <q-btn flat no-caps icon="content_copy" label="Copy" @click="copy" />
        <q-btn flat no-caps icon="open_in_new" label="Open in mail app" :href="mailto" target="_blank" :disable="!client?.email">
          <q-tooltip v-if="!client?.email">Add an email address to the client first</q-tooltip>
        </q-btn>
        <q-space />
        <q-btn unelevated no-caps color="secondary" icon="task_alt" label="Log as sent" :loading="logging" @click="logSent" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuasar, copyToClipboard } from 'quasar'
import { useCrmStore } from 'src/stores/crm'
import { useAuthStore } from 'src/stores/auth'
import type { Client, EmailPurpose } from 'src/types/crm'
import { errorMessage } from 'src/utils/errors'

const props = defineProps<{ modelValue: boolean; client: Client | null; initialPurpose?: EmailPurpose }>()
const emit = defineEmits<{ (e: 'update:modelValue', open: boolean): void }>()

const PURPOSES: Array<{ value: EmailPurpose; label: string; icon: string }> = [
  { value: 'follow_up', label: 'Follow-up', icon: 'reply' },
  { value: 'vr_invite', label: 'VR walkthrough', icon: 'view_in_ar' },
  { value: 'proposal', label: 'Proposal', icon: 'request_quote' },
  { value: 'progress_update', label: 'Progress update', icon: 'construction' },
  { value: 'change_order', label: 'Change order', icon: 'published_with_changes' },
  { value: 'custom', label: 'Other', icon: 'edit' }
]

const $q = useQuasar()
const crm = useCrmStore()
const auth = useAuthStore()

const purpose = ref<EmailPurpose>('follow_up')
const notes = ref('')
const subject = ref('')
const body = ref('')
const source = ref('')
const drafting = ref(false)
const logging = ref(false)
const error = ref<string | null>(null)

const onShow = () => {
  purpose.value = props.initialPurpose ?? 'follow_up'
  notes.value = ''
  subject.value = body.value = source.value = ''
  error.value = null
}

const draft = async () => {
  if (!props.client) return
  drafting.value = true
  error.value = null
  try {
    const result = await crm.draftEmail(props.client.id, purpose.value, notes.value, auth.fullName || undefined)
    subject.value = result.subject
    body.value = result.body
    source.value = result.source
  } catch (err) {
    error.value = errorMessage(err, 'Could not draft the email')
  } finally {
    drafting.value = false
  }
}

const mailto = computed(() =>
  props.client?.email
    ? `mailto:${encodeURIComponent(props.client.email)}?subject=${encodeURIComponent(subject.value)}&body=${encodeURIComponent(body.value)}`
    : undefined
)

const copy = async () => {
  await copyToClipboard(`Subject: ${subject.value}\n\n${body.value}`)
  $q.notify({ type: 'positive', message: 'Copied' })
}

const logSent = async () => {
  if (!props.client) return
  logging.value = true
  try {
    await crm.logActivity(props.client.id, {
      kind: 'email',
      summary: subject.value || 'Email sent',
      details: body.value,
      author: auth.fullName || null
    })
    $q.notify({ type: 'positive', message: 'Logged on the client timeline' })
    emit('update:modelValue', false)
  } catch (err) {
    error.value = errorMessage(err, 'Could not log the email')
  } finally {
    logging.value = false
  }
}
</script>
