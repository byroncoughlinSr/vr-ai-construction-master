<template>
  <q-page class="flex flex-center">
    <q-card class="q-pa-lg" style="min-width: 400px;">
      <q-card-section>
        <div class="text-center q-mb-md">
          <q-icon name="home_work" size="48px" color="primary" />
          <div class="text-h5 q-mt-sm">VR Construction Platform</div>
          <div class="text-grey-6">Sign in to your account</div>
        </div>

        <q-form @submit="onSubmit" class="q-gutter-md">
          <q-input
            v-model="form.username"
            label="Username"
            outlined
            :rules="[val => val && val.length > 0 || 'Username is required']"
            :loading="loading"
          />

          <q-input
            v-model="form.password"
            type="password"
            label="Password"
            outlined
            :rules="[val => val && val.length > 0 || 'Password is required']"
            :loading="loading"
          />

          <q-btn
            type="submit"
            label="Sign In"
            color="primary"
            :loading="loading"
            class="full-width q-mt-md"
          />
        </q-form>

        <div class="text-center q-mt-md">
          <q-btn flat label="Forgot Password?" color="primary" />
        </div>
      </q-card-section>

      <q-card-section v-if="error" class="q-pt-none">
        <q-banner class="bg-negative text-white" rounded>
          <template v-slot:avatar>
            <q-icon name="error" />
          </template>
          {{ error }}
        </q-banner>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useAuthStore } from 'stores/auth'

const router = useRouter()
const $q = useQuasar()
const authStore = useAuthStore()

const loading = ref(false)
const error = ref<string | null>(null)

const form = reactive({
  username: '',
  password: ''
})

const onSubmit = async () => {
  loading.value = true
  error.value = null

  try {
    await authStore.login(form)
    $q.notify({
      type: 'positive',
      message: 'Login successful'
    })
    router.push('/')
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}
</script>

<style lang="sass" scoped>
.full-width
  width: 100%
</style>
