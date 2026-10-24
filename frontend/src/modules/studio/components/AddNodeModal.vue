<script setup>
import { reactive, ref } from 'vue'
import { navApi } from '../../../api'
import { X, GitFork } from 'lucide-vue-next'

const props = defineProps({
  floorId: [String, Number],
  coords: Object, // { x, y }
})
const emit = defineEmits(['close', 'created'])

const NODE_TYPES = [
  { value: 'corridor',  label: '🛤 Коридор' },
  { value: 'door',      label: '🚪 Дверь' },
  { value: 'stairs',    label: '🪜 Лестница' },
  { value: 'elevator',  label: '🛗 Лифт' },
]

const form = reactive({
  node_type: 'corridor',
  is_accessible: true,
})
const loading = ref(false)
const error = ref('')

async function handleCreate() {
  loading.value = true
  error.value = ''
  try {
    await navApi.createNode(props.floorId, {
      node_type: form.node_type,
      is_accessible: form.is_accessible,
      x_coord: props.coords.x,
      y_coord: props.coords.y,
    })
    emit('created')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Ошибка'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4" style="background: rgba(0,0,0,0.6); backdrop-filter: blur(4px)">
    <div class="card w-full max-w-xs p-6 slide-up" @click.stop>
      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-2">
          <GitFork :size="16" style="color: #a78bfa" />
          <h3 class="font-semibold text-sm" style="color: var(--text-primary)">Новый узел графа</h3>
        </div>
        <button @click="$emit('close')" class="btn btn-ghost p-1"><X :size="14" /></button>
      </div>

      <form @submit.prevent="handleCreate" class="space-y-4">
        <div>
          <label class="label">Тип узла</label>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="t in NODE_TYPES"
              :key="t.value"
              type="button"
              @click="form.node_type = t.value"
              class="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all text-left"
              :style="form.node_type === t.value
                ? 'background: rgba(139,92,246,0.2); color: #a78bfa; border: 1px solid rgba(139,92,246,0.4);'
                : 'background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--border);'"
            >
              {{ t.label }}
            </button>
          </div>
        </div>

        <label class="flex items-center gap-2.5 cursor-pointer">
          <input type="checkbox" v-model="form.is_accessible" class="w-4 h-4 accent-blue-500 rounded" />
          <span class="text-sm" style="color: var(--text-secondary)">Доступно для МГН / колясочников</span>
        </label>

        <div class="text-xs font-mono px-2 py-1 rounded" style="background: var(--bg-surface); color: var(--text-muted)">
          x={{ coords.x.toFixed(0) }}, y={{ coords.y.toFixed(0) }}
        </div>

        <div v-if="error" class="p-2 rounded text-xs" style="background: rgba(239,68,68,0.1); color: #f87171">{{ error }}</div>

        <div class="flex gap-2">
          <button type="button" @click="$emit('close')" class="btn btn-ghost flex-1 justify-center text-xs">Отмена</button>
          <button id="node-submit" type="submit" :disabled="loading" class="btn text-xs flex-1 justify-center" style="background: #7c3aed; color: white">
            <span v-if="loading" class="spinner w-3 h-3"></span>
            {{ loading ? '...' : 'Добавить' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
