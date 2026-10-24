<script setup>
import { ref, reactive } from 'vue'
import { spacesApi } from '../../../api'
import { X } from 'lucide-vue-next'

const emit = defineEmits(['close', 'created'])
const form = reactive({ name: '', slug: '', description: '' })
const loading = ref(false)
const error = ref('')

function autoSlug() {
  form.slug = form.name
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
}

async function handleCreate() {
  loading.value = true
  error.value = ''
  try {
    await spacesApi.create({ title: form.name, slug: form.slug, description: form.description })
    emit('created')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Ошибка создания'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <!-- Backdrop -->
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4" style="background: rgba(0,0,0,0.6); backdrop-filter: blur(4px)">
    <div class="card w-full max-w-md p-6 slide-up" @click.stop>
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <h2 class="text-lg font-semibold" style="color: var(--text-primary)">Новое пространство</h2>
        <button @click="$emit('close')" class="btn btn-ghost p-1.5">
          <X :size="18" />
        </button>
      </div>

      <form @submit.prevent="handleCreate" class="space-y-4">
        <div>
          <label class="label">Название *</label>
          <input id="space-name" v-model="form.name" @input="autoSlug" type="text" class="input" placeholder="Хакатон ТТК 2026" required />
        </div>
        <div>
          <label class="label">URL-идентификатор (slug) *</label>
          <input id="space-slug" v-model="form.slug" type="text" class="input font-mono" placeholder="hakaton-ttk-2026" required pattern="[a-z0-9\-]+" title="Только латинские буквы, цифры и тире" />
          <p class="text-xs mt-1" style="color: var(--text-muted)">Ссылка: /space/<b>{{ form.slug || 'slug' }}</b></p>
        </div>
        <div>
          <label class="label">Описание</label>
          <textarea id="space-desc" v-model="form.description" class="input resize-none" rows="3" placeholder="Краткое описание мероприятия или объекта..."></textarea>
        </div>

        <div v-if="error" class="flex items-center gap-2 p-3 rounded-lg text-sm" style="background: rgba(239,68,68,0.1); color: #f87171; border: 1px solid rgba(239,68,68,0.2)">
          {{ error }}
        </div>

        <div class="flex gap-3 pt-2">
          <button type="button" @click="$emit('close')" class="btn btn-ghost flex-1 justify-center">Отмена</button>
          <button id="space-create-submit" type="submit" :disabled="loading" class="btn btn-primary flex-1 justify-center">
            <span v-if="loading" class="spinner w-4 h-4"></span>
            {{ loading ? 'Создание...' : 'Создать' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
