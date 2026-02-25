<template>
  <q-card class="vr-view-card">
    <q-card-section>
      <div class="row items-center">
        <q-icon name="view_in_ar" size="48px" color="primary" class="q-mr-md" />
        <div class="col">
          <div class="text-h6">View in VR</div>
          <div class="text-caption text-grey-7">
            Experience this project in virtual reality on your Meta Quest device
          </div>
        </div>
      </div>
    </q-card-section>

    <q-card-section>
      <q-btn
        color="primary"
        icon="360"
        label="Generate VR Model"
        @click="generateVRModel"
        :loading="loading"
        :disable="!projectId || loading"
        class="full-width q-mb-md"
        size="lg"
      />

      <div v-if="qrCodeUrl" class="text-center q-mt-md">
        <div class="text-subtitle2 q-mb-sm">Scan with Quest to View</div>
        <q-img
          :src="qrCodeUrl"
          style="max-width: 200px; margin: 0 auto;"
          class="q-mb-sm"
        />
        <div class="text-caption text-grey-7">
          Open Construction Quest app on your Meta Quest and scan this QR code
        </div>
      </div>

      <div v-if="vrUrl" class="q-mt-md">
        <q-separator class="q-my-md" />
        <div class="text-subtitle2 q-mb-sm">Direct Link</div>
        <q-input
          :model-value="vrUrl"
          readonly
          outlined
          dense
        >
          <template v-slot:append>
            <q-btn
              flat
              dense
              icon="content_copy"
              @click="copyToClipboard"
              color="primary"
            >
              <q-tooltip>Copy to clipboard</q-tooltip>
            </q-btn>
          </template>
        </q-input>
        <div class="text-caption text-grey-7 q-mt-xs">
          Project ID: {{ projectId }} | Rooms: {{ roomCount }} | Ready for VR
        </div>
      </div>
    </q-card-section>

    <q-card-section v-if="error">
      <q-banner class="bg-negative text-white" dense>
        <template v-slot:avatar>
          <q-icon name="error" />
        </template>
        {{ error }}
      </q-banner>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useQuasar } from 'quasar'
import { apiClient } from 'src/services/api'

interface Props {
  projectId?: number
}

const props = defineProps<Props>()
const $q = useQuasar()

const loading = ref(false)
const error = ref<string | null>(null)
const vrUrl = ref<string | null>(null)
const qrCodeUrl = ref<string | null>(null)
const roomCount = ref(0)

const generateVRModel = async () => {
  if (!props.projectId) {
    error.value = 'No project selected'
    return
  }

  loading.value = true
  error.value = null

  try {
    // Call backend to generate VR geometry
    const response = await apiClient.client.get(`/projects/${props.projectId}/generate-vr`)

    if (response.data.success) {
      const geometry = response.data.geometry
      roomCount.value = geometry.metadata?.total_rooms || 0

      // Generate deep link URL for Quest app
      vrUrl.value = `constructionquest://project/${props.projectId}`

      // Generate QR code (using a QR code API)
      const qrData = encodeURIComponent(vrUrl.value)
      qrCodeUrl.value = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${qrData}`

      $q.notify({
        type: 'positive',
        message: 'VR model generated successfully!',
        caption: `${roomCount.value} rooms ready to explore`,
        icon: 'check_circle'
      })
    } else {
      throw new Error('Failed to generate VR geometry')
    }
  } catch (err) {
    error.value = (err as Error).message || 'Failed to generate VR model'
    $q.notify({
      type: 'negative',
      message: 'VR Generation Failed',
      caption: error.value
    })
  } finally {
    loading.value = false
  }
}

const copyToClipboard = () => {
  if (vrUrl.value) {
    navigator.clipboard.writeText(vrUrl.value)
    $q.notify({
      type: 'positive',
      message: 'Link copied to clipboard!',
      icon: 'content_copy'
    })
  }
}
</script>

<style lang="sass" scoped>
.vr-view-card
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%)
  color: white

  .q-icon
    color: white !important

  .text-grey-7
    color: rgba(255, 255, 255, 0.7) !important
</style>
