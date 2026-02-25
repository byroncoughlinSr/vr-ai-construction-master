<template>
  <div class="ai-image-generator q-pa-md">
    <q-card class="q-pa-md">
      <q-card-section>
        <div class="text-h6">AI Image Generator</div>
        <div class="text-subtitle2 text-grey-7">
          Generate architectural visualizations with real-time progress tracking
        </div>
      </q-card-section>

      <q-card-section>
        <!-- Prompt Input -->
        <q-input
          v-model="prompt"
          label="Image Prompt"
          placeholder="e.g., modern house with large windows"
          outlined
          type="textarea"
          rows="3"
          :disable="isGenerating"
          class="q-mb-md"
        >
          <template v-slot:prepend>
            <q-icon name="edit" />
          </template>
        </q-input>

        <!-- Advanced Options -->
        <q-expansion-item label="Advanced Options" class="q-mb-md">
          <q-card>
            <q-card-section>
              <div class="row q-col-gutter-md">
                <div class="col-6">
                  <q-input
                    v-model.number="width"
                    label="Width"
                    type="number"
                    outlined
                    dense
                    :disable="isGenerating"
                  />
                </div>
                <div class="col-6">
                  <q-input
                    v-model.number="height"
                    label="Height"
                    type="number"
                    outlined
                    dense
                    :disable="isGenerating"
                  />
                </div>
                <div class="col-6">
                  <q-input
                    v-model.number="steps"
                    label="Inference Steps"
                    type="number"
                    outlined
                    dense
                    :disable="isGenerating"
                  />
                </div>
                <div class="col-6">
                  <q-input
                    v-model.number="guidanceScale"
                    label="Guidance Scale"
                    type="number"
                    step="0.1"
                    outlined
                    dense
                    :disable="isGenerating"
                  />
                </div>
              </div>
            </q-card-section>
          </q-card>
        </q-expansion-item>

        <!-- Generate Button -->
        <q-btn
          @click="generateImage"
          :loading="isGenerating"
          :disable="!prompt || isGenerating"
          color="primary"
          icon="auto_awesome"
          label="Generate Image"
          class="full-width"
          size="lg"
        />

        <!-- Progress Section -->
        <div v-if="isGenerating" class="q-mt-lg">
          <div class="text-subtitle1 q-mb-sm">
            Generating Image...
          </div>

          <!-- Progress Bar -->
          <q-linear-progress
            :value="progress.percentage / 100"
            color="primary"
            size="25px"
            class="q-mb-sm"
          >
            <div class="absolute-full flex flex-center">
              <q-badge
                color="white"
                text-color="primary"
                :label="`${progress.step} / ${progress.total_steps} steps (${progress.percentage}%)`"
              />
            </div>
          </q-linear-progress>

          <!-- Status Text -->
          <div class="text-caption text-grey-7 text-center">
            {{ statusText }}
          </div>
        </div>

        <!-- Error Display -->
        <q-banner v-if="error" class="bg-negative text-white q-mt-md" rounded>
          <template v-slot:avatar>
            <q-icon name="error" />
          </template>
          {{ error }}
        </q-banner>

        <!-- Success Message -->
        <q-banner
          v-if="generatedImageUrl && !isGenerating"
          class="bg-positive text-white q-mt-md"
          rounded
        >
          <template v-slot:avatar>
            <q-icon name="check_circle" />
          </template>
          Image generated successfully!
        </q-banner>
      </q-card-section>

      <!-- Generated Image Display -->
      <q-card-section v-if="generatedImageUrl">
        <div class="text-subtitle1 q-mb-md">Generated Image</div>
        <q-img
          :src="generatedImageUrl"
          :ratio="width / height"
          class="rounded-borders"
          style="max-width: 100%"
        >
          <template v-slot:loading>
            <q-spinner-gears color="primary" />
          </template>
        </q-img>

        <!-- Action Buttons -->
        <div class="q-mt-md row q-gutter-sm">
          <q-btn
            @click="downloadImage"
            icon="download"
            label="Download"
            color="primary"
            outline
          />
          <q-btn
            @click="resetGenerator"
            icon="refresh"
            label="Generate Another"
            color="secondary"
            outline
          />
        </div>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue';
import { apiClient } from '@/services/api';
import { ImageProgressService, type ImageProgress } from '@/services/imageProgress';

// Component state
const prompt = ref('');
const width = ref(768);
const height = ref(512);
const steps = ref(50);
const guidanceScale = ref(8.0);

const isGenerating = ref(false);
const progress = ref<ImageProgress>({
  generation_id: '',
  step: 0,
  total_steps: 0,
  percentage: 0,
  status: 'generating'
});

const generatedImageUrl = ref('');
const currentGenerationId = ref('');
const error = ref('');

// Progress service instance
const progressService = new ImageProgressService();

// Computed properties
const statusText = computed(() => {
  if (!isGenerating.value) return '';
  
  const elapsed = progress.value.step;
  const total = progress.value.total_steps;
  
  if (elapsed === 0) return 'Initializing model...';
  if (elapsed < total * 0.25) return 'Starting generation...';
  if (elapsed < total * 0.75) return 'Processing image...';
  return 'Finalizing...';
});

/**
 * Generate an image using the AI service
 */
async function generateImage() {
  if (!prompt.value) {
    error.value = 'Please enter a prompt';
    return;
  }

  // Reset state
  isGenerating.value = true;
  error.value = '';
  generatedImageUrl.value = '';
  progress.value = {
    generation_id: '',
    step: 0,
    total_steps: 0,
    percentage: 0,
    status: 'generating'
  };

  try {
    // Start image generation
    const response = await apiClient.client.post('/api/v1/ai-image/generate', {
      prompt: prompt.value,
      width: width.value,
      height: height.value,
      num_inference_steps: steps.value,
      guidance_scale: guidanceScale.value
    });

    const data = response.data;
    currentGenerationId.value = data.generation_id;

    console.log(`[AIImageGenerator] Started generation ${data.generation_id}`);

    // Connect to progress WebSocket
    progressService.connect(
      data.generation_id,
      handleProgressUpdate,
      getWebSocketUrl()
    );

    // Store the image URL from response
    // (will be displayed when progress completes)
    if (data.images && data.images.length > 0) {
      generatedImageUrl.value = getFullImageUrl(data.images[0].image_url);
    }

  } catch (err: any) {
    console.error('[AIImageGenerator] Generation failed:', err);
    error.value = err.response?.data?.detail || 'Failed to generate image';
    isGenerating.value = false;
    progressService.disconnect();
  }
}

/**
 * Handle progress updates from WebSocket
 */
function handleProgressUpdate(progressData: ImageProgress) {
  progress.value = progressData;

  if (progressData.status === 'completed') {
    console.log('[AIImageGenerator] Generation completed');
    isGenerating.value = false;
  } else if (progressData.status === 'failed') {
    console.error('[AIImageGenerator] Generation failed');
    error.value = 'Image generation failed. Please try again.';
    isGenerating.value = false;
  }
}

/**
 * Download the generated image
 */
function downloadImage() {
  if (!generatedImageUrl.value) return;

  const link = document.createElement('a');
  link.href = generatedImageUrl.value;
  link.download = `generated-image-${Date.now()}.png`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

/**
 * Reset the generator for a new image
 */
function resetGenerator() {
  generatedImageUrl.value = '';
  error.value = '';
  progress.value = {
    generation_id: '',
    step: 0,
    total_steps: 0,
    percentage: 0,
    status: 'generating'
  };
}

/**
 * Get WebSocket URL based on current environment
 */
function getWebSocketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname;
  const port = import.meta.env.VITE_API_PORT || '8000';
  return `${protocol}//${host}:${port}`;
}

/**
 * Get full image URL
 */
function getFullImageUrl(imagePath: string): string {
  if (imagePath.startsWith('http')) return imagePath;
  
  const protocol = window.location.protocol;
  const host = window.location.hostname;
  const port = import.meta.env.VITE_API_PORT || '8000';
  return `${protocol}//${host}:${port}${imagePath}`;
}

// Cleanup on component unmount
onUnmounted(() => {
  progressService.disconnect();
});
</script>

<style scoped lang="scss">
.ai-image-generator {
  max-width: 800px;
  margin: 0 auto;
}

.rounded-borders {
  border-radius: 8px;
  overflow: hidden;
}
</style>
