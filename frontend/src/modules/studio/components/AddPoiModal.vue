<script setup>
import { reactive, ref } from 'vue'
import { poisApi } from '../../../api'
import { X, MapPin } from 'lucide-vue-next'

const props = defineProps({
  floorId: [String, Number],
  coords: Object, // { x, y }
})
const emit = defineEmits(['close', 'created'])

const CATEGORIES = [
  { value: 'stand',    label: '🏢 Стенд' },
  { value: 'cafe',     label: '☕ Кафе / Еда' },
  { value: 'toilet',   label: '🚻 Туалет' },
  { value: 'wifi',     label: '📶 Wi-Fi' },
  { value: 'stage',    label: '🎤 Сцена' },
  { value: 'entrance', label: '🚪 Вход / Выход' },
  { value: 'other',    label: '📍 Другое' },
]

const form = reactive({
  name: '',
  category: 'stand',
  description: '',
})
const loading = ref(false)
const error = ref('')

async function handleCreate() {
  if (!form.name) return
  loading.value = true
  error.value = ''
  try {
    await poisApi.create(props.floorId, {
      name: form.name,
      category: form.category,
      description: form.description,
      x_coord: props.coords.x,
      y_coord: props.coords.y,
    })
    emit('created')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Ошибка создания'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4" style="background: rgba(0,0,0,0.6); backdrop-filter: blur(4px)">
    <div class="card w-full max-w-sm p-6 slide-up" @click.stop>
      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-2">
          <MapPin :size="18" style="color: var(--accent)" />
          <h3 class="font-semibold" style="color: var(--text-primary)">Добавить точку интереса</h3>
        </div>
        <button @click="$emit('close')" class="btn btn-ghost p-1.5"><X :size="16" /></button>
      </div>

      <form @submit.prevent="handleCreate" class="space-y-4">
        <div>
          <label class="label">Название *</label>
          <input id="poi-name" v-model="form.name" type="text" class="input" placeholder="Стенд Газпром / Кофе-зона" required autofocus />
        </div>

        <div>
          <label class="label">Категория</label>
          <select id="poi-category" v-model="form.category" class="input">
            <option v-for="c in CATEGORIES" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </div>

        <div>
          <label class="label">Описание</label>
          <textarea v-model="form.description" class="input resize-none" rows="2" placeholder="Краткое описание..."></textarea>
        </div>

        <div class="text-xs font-mono px-2 py-1 rounded" style="background: var(--bg-surface); color: var(--text-muted)">
          x={{ coords.x.toFixed(0) }}, y={{ coords.y.toFixed(0) }}
        </div>

        <div v-if="error" class="p-2 rounded text-xs" style="background: rgba(239,68,68,0.1); color: #f87171">{{ error }}</div>

        <div class="flex gap-3">
          <button type="button" @click="$emit('close')" class="btn btn-ghost flex-1 justify-center text-sm">Отмена</button>
          <button id="poi-submit" type="submit" :disabled="loading" class="btn btn-primary flex-1 justify-center text-sm">
            <span v-if="loading" class="spinner w-3.5 h-3.5"></span>
            {{ loading ? 'Сохранение...' : 'Добавить' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
