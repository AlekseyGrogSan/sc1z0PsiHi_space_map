<script setup>
import { ref } from 'vue'
import { floorsApi } from '../../../api'
import {
  MousePointer2, MapPin, GitFork, Upload, Ruler, ChevronDown,
  Plus, Check, X, Layers, Info
} from 'lucide-vue-next'

const props = defineProps({
  space: Object,
  floors: Array,
  currentFloor: Object,
  mode: String,
  calibrating: Boolean,
  calibResult: Object,
  selectedNode: Object,
  calibDistance: String,
})
const emit = defineEmits([
  'select-floor', 'floor-created', 'upload-plan', 'set-mode',
  'start-calib', 'save-calib', 'cancel-calib', 'update:calibDistance',
])

const showAddFloor = ref(false)
const newFloorName = ref('')
const newFloorLevel = ref(1)
const addingFloor = ref(false)

async function createFloor() {
  if (!newFloorName.value || !props.space) return
  addingFloor.value = true
  try {
    const { data } = await floorsApi.create(props.space.id, {
      name: newFloorName.value,
      level: Number(newFloorLevel.value),
    })
    emit('floor-created', data)
    showAddFloor.value = false
    newFloorName.value = ''
    newFloorLevel.value = 1
  } catch (e) {
    console.error(e)
  } finally {
    addingFloor.value = false
  }
}

const NODE_TYPE_LABELS = {
  corridor: { label: 'Коридор', color: '#64748b' },
  door: { label: 'Дверь', color: '#f59e0b' },
  stairs: { label: 'Лестница', color: '#8b5cf6' },
  elevator: { label: 'Лифт', color: '#06b6d4' },
}
</script>

<template>
  <aside class="flex flex-col w-72 shrink-0 overflow-y-auto" style="background: var(--bg-card); border-right: 1px solid var(--border)">
    <!-- Space info -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <p class="text-xs font-medium mb-0.5" style="color: var(--text-muted)">Пространство</p>
      <p class="font-semibold text-sm leading-tight" style="color: var(--text-primary)">{{ space?.name || '...' }}</p>
    </div>

    <!-- Floors list -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <div class="flex items-center justify-between mb-2">
        <p class="text-xs font-medium uppercase tracking-wider" style="color: var(--text-muted)">Этажи</p>
        <button @click="showAddFloor = !showAddFloor" class="btn btn-ghost p-1 rounded" title="Добавить этаж">
          <Plus :size="14" />
        </button>
      </div>

      <!-- Add floor form -->
      <div v-if="showAddFloor" class="mb-3 p-3 rounded-lg space-y-2" style="background: var(--bg-surface)">
        <input v-model="newFloorName" type="text" class="input text-xs py-1.5" placeholder="Название этажа" />
        <input v-model="newFloorLevel" type="number" class="input text-xs py-1.5" placeholder="Уровень (1, 2, -1...)" />
        <div class="flex gap-2">
          <button @click="createFloor" :disabled="addingFloor" class="btn btn-primary flex-1 justify-center text-xs py-1">
            <span v-if="addingFloor" class="spinner w-3 h-3"></span>
            <Check v-else :size="12" />
            Создать
          </button>
          <button @click="showAddFloor = false" class="btn btn-ghost flex-1 justify-center text-xs py-1">
            <X :size="12" /> Отмена
          </button>
        </div>
      </div>

      <!-- Floor buttons -->
      <div class="space-y-1">
        <button
          v-for="floor in floors"
          :key="floor.id"
          :id="`floor-tab-${floor.id}`"
          @click="$emit('select-floor', floor)"
          class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all text-left"
          :style="currentFloor?.id === floor.id
            ? 'background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.3);'
            : 'color: var(--text-secondary); border: 1px solid transparent;'"
        >
          <Layers :size="14" />
          <span class="flex-1 truncate">{{ floor.name }}</span>
          <span class="text-xs font-mono px-1.5 py-0.5 rounded" style="background: var(--bg-surface); color: var(--text-muted)">{{ floor.level > 0 ? '+' : '' }}{{ floor.level }}</span>
          <span v-if="floor.plan_image_url" class="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0"></span>
          <span v-else class="w-1.5 h-1.5 rounded-full shrink-0" style="background: var(--border)"></span>
        </button>
      </div>
    </div>

    <!-- Plan upload -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <p class="text-xs font-medium uppercase tracking-wider mb-2" style="color: var(--text-muted)">План этажа</p>
      <button
        id="upload-plan-btn"
        @click="$emit('upload-plan')"
        :disabled="!currentFloor"
        class="btn btn-ghost w-full justify-start text-sm gap-2.5"
      >
        <Upload :size="15" />
        {{ currentFloor?.plan_image_url ? 'Заменить план' : 'Загрузить план' }}
      </button>
    </div>

    <!-- Edit mode -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <p class="text-xs font-medium uppercase tracking-wider mb-2" style="color: var(--text-muted)">Режим редактирования</p>
      <div class="space-y-1">
        <button
          id="mode-view"
          @click="$emit('set-mode', 'view')"
          class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all text-left"
          :style="mode === 'view' ? 'background: rgba(100,116,139,0.2); color: var(--text-primary);' : 'color: var(--text-secondary);'"
        >
          <MousePointer2 :size="14" />
          Просмотр / Перемещение
        </button>
        <button
          id="mode-poi"
          @click="$emit('set-mode', 'poi')"
          :disabled="!currentFloor?.plan_image_url"
          class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all text-left disabled:opacity-40"
          :style="mode === 'poi' ? 'background: rgba(59,130,246,0.15); color: #60a5fa;' : 'color: var(--text-secondary);'"
        >
          <MapPin :size="14" />
          Точки интереса (POI)
        </button>
        <button
          id="mode-nav"
          @click="$emit('set-mode', 'nav')"
          :disabled="!currentFloor?.plan_image_url"
          class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all text-left disabled:opacity-40"
          :style="mode === 'nav' ? 'background: rgba(139,92,246,0.15); color: #a78bfa;' : 'color: var(--text-secondary);'"
        >
          <GitFork :size="14" />
          Навигационный граф
        </button>
      </div>

      <!-- Nav legend -->
      <div v-if="mode === 'nav'" class="mt-3 p-3 rounded-lg space-y-1.5" style="background: var(--bg-surface)">
        <p class="text-xs font-medium mb-2" style="color: var(--text-muted)">Типы узлов</p>
        <div v-for="(v, k) in NODE_TYPE_LABELS" :key="k" class="flex items-center gap-2 text-xs" style="color: var(--text-secondary)">
          <span class="w-3 h-3 rounded-full shrink-0" :style="`background: ${v.color}`"></span>
          {{ v.label }}
        </div>
        <div v-if="selectedNode" class="mt-2 p-2 rounded text-xs" style="background: rgba(245,158,11,0.1); color: #fbbf24; border: 1px solid rgba(245,158,11,0.2)">
          Выбран узел #{{ selectedNode.id }} — кликните второй узел
        </div>
      </div>
    </div>

    <!-- Calibration -->
    <div class="px-4 py-3">
      <p class="text-xs font-medium uppercase tracking-wider mb-2" style="color: var(--text-muted)">Масштаб (PPM)</p>

      <div v-if="!calibrating && !calibResult">
        <button
          id="start-calib-btn"
          @click="$emit('start-calib')"
          :disabled="!currentFloor?.plan_image_url"
          class="btn btn-ghost w-full justify-start text-sm gap-2.5 disabled:opacity-40"
        >
          <Ruler :size="15" />
          Задать масштаб
        </button>
        <p v-if="currentFloor?.pixels_per_meter" class="text-xs mt-2" style="color: var(--text-muted)">
          Текущий: <b style="color: var(--text-secondary)">{{ currentFloor.pixels_per_meter?.toFixed(2) }} px/м</b>
        </p>
      </div>

      <div v-if="calibrating" class="p-3 rounded-lg text-sm" style="background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.25); color: #fbbf24">
        <p class="font-medium mb-1">🎯 Режим калибровки</p>
        <p class="text-xs" style="color: #fcd34d">Кликните 2 точки на плане с известным расстоянием</p>
        <button @click="$emit('cancel-calib')" class="btn btn-ghost text-xs mt-2 py-1 w-full justify-center">Отмена</button>
      </div>

      <div v-if="calibResult && !calibrating" class="p-3 rounded-lg space-y-2" style="background: var(--bg-surface)">
        <p class="text-xs" style="color: var(--text-muted)">Расстояние: <b style="color:var(--text-secondary)">{{ calibResult.pixels.toFixed(1) }} px</b></p>
        <label class="label">Реальное расстояние (м)</label>
        <input
          type="number"
          step="0.01"
          min="0.01"
          class="input text-xs py-1.5"
          placeholder="например 0.9"
          :value="calibDistance"
          @input="$emit('update:calibDistance', $event.target.value)"
        />
        <div class="flex gap-2">
          <button @click="$emit('save-calib')" class="btn btn-primary text-xs py-1 flex-1 justify-center">
            <Check :size="12" /> Сохранить
          </button>
          <button @click="$emit('cancel-calib')" class="btn btn-ghost text-xs py-1 flex-1 justify-center">
            <X :size="12" /> Отмена
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>
