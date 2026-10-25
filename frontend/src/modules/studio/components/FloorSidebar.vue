<script setup>
import { ref } from 'vue'
import { floorsApi } from '../../../api'
import {
  MousePointer2, Square, Minus, Circle, Box, Footprints, MapPin,
  Zap, Eye, EyeOff, Sliders, Ruler, Trash2,
  Layers, Plus, Check, X, Upload, Shapes, Wand2, Magnet,
  RotateCw, RotateCcw
} from 'lucide-vue-next'

const props = defineProps({
  space: Object,
  floors: Array,
  currentFloor: Object,
  mode: String,
  calibrating: Boolean,
  calibResult: Object,
  calibDistance: String,
  blueprintOpacity: {
    type: Number,
    default: 0.85,
  },
  blueprintRotation: {
    type: Number,
    default: 0,
  },
  showGraph: {
    type: Boolean,
    default: false,
  },
  graphStats: {
    type: Object,
    default: () => ({ nodes: 0, edges: 0 }),
  },
  generatingGraph: {
    type: Boolean,
    default: false,
  },
  layoutCounts: {
    type: Object,
    default: () => ({ rooms: 0, walls: 0, obstacles: 0, corridors: 0, pois: 0 }),
  },
  corridorWidth: {
    type: Number,
    default: 35,
  },
  isGraphDirty: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits([
  'select-floor', 'floor-created', 'upload-plan', 'set-mode',
  'auto-graph', 'toggle-show-graph', 'update:blueprintOpacity',
  'clear-layout', 'start-calib', 'save-calib', 'cancel-calib',
  'update:calibDistance', 'update:corridorWidth', 'delete-plan', 'close-mobile',
  'align-walls', 'walls-to-room', 'rotate-plan',
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
      title: newFloorName.value,
      floor_number: Number(newFloorLevel.value),
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

const BUILDER_MODES = [
  { id: 'view', label: 'Просмотр / Выбор', icon: MousePointer2, color: 'text-slate-300', bg: 'rgba(100,116,139,0.2)' },
  { id: 'room', label: 'Зона (прямоугольник)', icon: Square, color: 'text-blue-400', bg: 'rgba(59,130,246,0.15)' },
  { id: 'poly-room', label: 'Зона (многоугольник)', icon: Shapes, color: 'text-indigo-400', bg: 'rgba(99,102,241,0.15)' },
  { id: 'wall', label: 'Стена', icon: Minus, color: 'text-slate-200', bg: 'rgba(148,163,184,0.2)' },
  { id: 'circle', label: 'Колонна / Круг', icon: Circle, color: 'text-cyan-400', bg: 'rgba(6,182,212,0.15)' },
  { id: 'rect', label: 'Препятствие / Стенд', icon: Box, color: 'text-amber-400', bg: 'rgba(245,158,11,0.15)' },
  { id: 'corridor', label: 'Проход / Коридор', icon: Footprints, color: 'text-emerald-400', bg: 'rgba(16,185,129,0.15)' },
  { id: 'poi', label: 'Точка интереса (POI)', icon: MapPin, color: 'text-rose-400', bg: 'rgba(244,63,94,0.15)' },
]
</script>

<template>
  <aside class="flex flex-col w-80 max-w-[85vw] h-full shrink-0 overflow-y-auto" style="background: var(--bg-card); border-right: 1px solid var(--border)">
    <!-- Space info -->
    <div class="px-4 py-3 border-b flex items-center justify-between" style="border-color: var(--border)">
      <div class="min-w-0 flex-1">
        <p class="text-xs font-medium mb-0.5" style="color: var(--text-muted)">Пространство</p>
        <p class="font-semibold text-sm leading-tight truncate" style="color: var(--text-primary)">
          {{ space?.title || space?.name || '...' }}
        </p>
      </div>
      <button
        type="button"
        @click="emit('close-mobile')"
        class="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors ml-2 shrink-0"
        title="Скрыть панель"
      >
        <X :size="16" />
      </button>
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
        <input v-model="newFloorName" type="text" class="input text-xs py-1.5" placeholder="Название этажа (1 этаж)" />
        <input v-model="newFloorLevel" type="number" class="input text-xs py-1.5" placeholder="Номер этажа (1, 2, -1...)" />
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
          <span class="flex-1 truncate">{{ floor.title || floor.name }}</span>
          <span class="text-xs font-mono px-1.5 py-0.5 rounded" style="background: var(--bg-surface); color: var(--text-muted)">
            {{ (floor.floor_number ?? floor.level) > 0 ? '+' : '' }}{{ floor.floor_number ?? floor.level }}
          </span>
          <span v-if="floor.plan_url || floor.plan_image_url" class="w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" title="Подложка загружена"></span>
          <span v-else class="w-1.5 h-1.5 rounded-full shrink-0" style="background: var(--border)" title="2D схема"></span>
        </button>
      </div>
    </div>

    <!-- 2D Room Builder Tools -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <div class="flex items-center justify-between mb-2">
        <p class="text-xs font-medium uppercase tracking-wider" style="color: var(--text-muted)">2D-Конструктор карты</p>
      </div>
      <div class="space-y-1">
        <button
          v-for="bMode in BUILDER_MODES"
          :key="bMode.id"
          :id="`mode-${bMode.id}`"
          @click="$emit('set-mode', bMode.id)"
          class="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all text-left"
          :style="mode === bMode.id ? `background: ${bMode.bg}; border: 1px solid rgba(255,255,255,0.15);` : 'color: var(--text-secondary); border: 1px solid transparent;'"
        >
          <component :is="bMode.icon" :size="15" :class="mode === bMode.id ? bMode.color : 'text-slate-400'" />
          <span :class="mode === bMode.id ? 'font-medium text-white' : ''">{{ bMode.label }}</span>
        </button>
      </div>

      <!-- Quick instructions per mode -->
      <div v-if="mode !== 'view'" class="mt-3 p-2.5 rounded-lg text-xs leading-relaxed" style="background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--border)">
        <p v-if="mode === 'room'">💡 <b>Зона / Комната:</b> кликните первый угол, затем второй угол для создания прямоугольной зоны.</p>
        <p v-if="mode === 'poly-room'">💡 <b>Многоугольная зона:</b> кликайте вершины для создания формы любой сложности (L-образные и др.). Клик рядом с началом или кнопка «Завершить» замыкает зону.</p>
        <p v-if="mode === 'wall'">💡 <b>Стена:</b> кликните начало стены, затем конец. Автоматическое выравнивание под 90° и примагничивание к углам.</p>
        <p v-if="mode === 'circle'">💡 <b>Колонна:</b> кликните на карте, чтобы поставить круглую колонну. Маршруты огибают её по касательной.</p>
        <p v-if="mode === 'rect'">💡 <b>Препятствие:</b> кликните два угла прямоугольного стенда или киоска.</p>
        <p v-if="mode === 'corridor'">💡 <b>Проход / Коридор:</b> кликните начало и конец основного прохода для приоритетной трассировки.</p>
        <p v-if="mode === 'poi'">💡 <b>POI:</b> кликните на карте для создания точки (вход, выход, лавочка, урна, магазин...).</p>
      </div>

      <!-- Wall Tools: Align & Glue, Convert Closed Walls to Room -->
      <div v-if="layoutCounts.walls >= 2" class="mt-3 pt-3 border-t border-slate-800/80 space-y-1.5">
        <div class="flex items-center justify-between mb-1">
          <p class="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Инструменты стен</p>
          <span class="text-[10px] text-indigo-400 font-mono">Smart Snap</span>
        </div>
        <button
          type="button"
          @click="$emit('align-walls')"
          class="w-full flex items-center justify-center gap-2 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800/90 hover:bg-slate-700/90 text-indigo-300 border border-indigo-500/30 hover:border-indigo-500/50 transition-all cursor-pointer shadow-sm active:scale-95"
          title="Выравнивает стены под 0°/90°, склеивает близкие стыки и объединяет отрезки в единые прямые"
        >
          <Wand2 :size="13" class="text-indigo-400 shrink-0" />
          <span>Выровнять и склеить стены</span>
        </button>
        <button
          v-if="layoutCounts.walls >= 3"
          type="button"
          @click="$emit('walls-to-room')"
          class="w-full flex items-center justify-center gap-2 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800/90 hover:bg-slate-700/90 text-blue-300 border border-blue-500/30 hover:border-blue-500/50 transition-all cursor-pointer shadow-sm active:scale-95"
          title="Находит замкнутый контур стен и превращает его в залитую зону/комнату со сложным контуром"
        >
          <Shapes :size="13" class="text-blue-400 shrink-0" />
          <span>Собрать зону из стен</span>
        </button>
      </div>

      <!-- Corridor Width Settings -->
      <div v-if="mode === 'corridor'" class="mt-3 p-3 rounded-lg space-y-2.5" style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25)">
        <div class="flex items-center justify-between text-xs">
          <span class="font-medium text-emerald-400">Ширина прохода:</span>
          <b class="font-mono text-emerald-300 font-bold">{{ corridorWidth }} px</b>
        </div>
        <input
          type="range"
          min="15"
          max="120"
          step="5"
          :value="corridorWidth"
          @input="$emit('update:corridorWidth', Number($event.target.value))"
          class="w-full accent-emerald-500 cursor-pointer h-1.5 rounded-lg bg-slate-700"
        />
        <div class="grid grid-cols-3 gap-1.5 text-[11px]">
          <button
            type="button"
            @click="$emit('update:corridorWidth', 20)"
            class="px-2 py-1 rounded text-center transition-all cursor-pointer"
            :style="corridorWidth === 20 ? 'background: #10b981; color: white;' : 'background: var(--bg-surface); color: var(--text-muted)'"
          >20px</button>
          <button
            type="button"
            @click="$emit('update:corridorWidth', 35)"
            class="px-2 py-1 rounded text-center transition-all cursor-pointer"
            :style="corridorWidth === 35 ? 'background: #10b981; color: white;' : 'background: var(--bg-surface); color: var(--text-muted)'"
          >35px</button>
          <button
            type="button"
            @click="$emit('update:corridorWidth', 60)"
            class="px-2 py-1 rounded text-center transition-all cursor-pointer"
            :style="corridorWidth === 60 ? 'background: #10b981; color: white;' : 'background: var(--bg-surface); color: var(--text-muted)'"
          >60px</button>
        </div>
      </div>
    </div>

    <!-- Navigation Auto-Graph (Backend) -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <div class="flex items-center justify-between mb-2">
        <p class="text-xs font-medium uppercase tracking-wider" style="color: var(--text-muted)">Навигационный граф</p>
        <span v-if="isGraphDirty" class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse">Нужен расчёт</span>
        <span v-else class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400 border border-blue-500/20">Актуален</span>
      </div>

      <div class="space-y-2">
        <button
          id="btn-auto-graph"
          @click="$emit('auto-graph')"
          :disabled="generatingGraph"
          class="btn w-full justify-center text-xs py-2 gap-2 font-semibold transition-all shadow-md active:scale-95"
          :class="isGraphDirty
            ? 'bg-amber-500 hover:bg-amber-400 text-slate-950 border border-amber-300 ring-2 ring-amber-400/30'
            : 'btn-primary'"
        >
          <span v-if="generatingGraph" class="spinner w-3.5 h-3.5" :class="isGraphDirty ? 'border-slate-950' : ''"></span>
          <Zap v-else :size="14" />
          {{ generatingGraph ? 'Расчёт путей...' : (isGraphDirty ? '⚡ Сохранить и пересчитать' : '⚡ Пересчитать граф') }}
        </button>

        <div class="flex items-center justify-between pt-1">
          <label class="flex items-center gap-2 text-xs cursor-pointer select-none" style="color: var(--text-secondary)">
            <input
              type="checkbox"
              :checked="showGraph"
              @change="$emit('toggle-show-graph', $event.target.checked)"
              class="rounded border-slate-700 text-blue-500 focus:ring-0 cursor-pointer"
            />
            <span>Показывать граф на карте</span>
          </label>
        </div>

        <div class="text-[11px] p-2 rounded bg-slate-900/60 border border-slate-800 text-slate-400 space-y-0.5">
          <div class="flex justify-between">
            <span>Узлов навигации:</span>
            <span class="font-mono text-slate-200 font-semibold">{{ graphStats.nodes }}</span>
          </div>
          <div class="flex justify-between">
            <span>Связей (рёбер):</span>
            <span class="font-mono text-slate-200 font-semibold">{{ graphStats.edges }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Layout elements statistics & Clear -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <div class="flex items-center justify-between mb-2">
        <p class="text-xs font-medium uppercase tracking-wider" style="color: var(--text-muted)">Элементы этажа</p>
        <button
          v-if="layoutCounts.rooms > 0 || layoutCounts.walls > 0 || layoutCounts.obstacles > 0 || layoutCounts.corridors > 0"
          @click="$emit('clear-layout')"
          class="text-xs text-rose-400 hover:text-rose-300 flex items-center gap-1 transition-colors"
          title="Очистить все векторные элементы"
        >
          <Trash2 :size="12" /> Очистить
        </button>
      </div>

      <div class="grid grid-cols-2 gap-1.5 text-xs text-slate-300">
        <div class="px-2 py-1.5 rounded bg-slate-900/50 border border-slate-800 flex justify-between items-center">
          <span class="text-slate-400">Зоны/комнаты:</span>
          <b class="font-mono text-blue-400">{{ layoutCounts.rooms }}</b>
        </div>
        <div class="px-2 py-1.5 rounded bg-slate-900/50 border border-slate-800 flex justify-between items-center">
          <span class="text-slate-400">Стены:</span>
          <b class="font-mono text-slate-300">{{ layoutCounts.walls }}</b>
        </div>
        <div class="px-2 py-1.5 rounded bg-slate-900/50 border border-slate-800 flex justify-between items-center">
          <span class="text-slate-400">Препятствия:</span>
          <b class="font-mono text-amber-400">{{ layoutCounts.obstacles }}</b>
        </div>
        <div class="px-2 py-1.5 rounded bg-slate-900/50 border border-slate-800 flex justify-between items-center">
          <span class="text-slate-400">Проходы:</span>
          <b class="font-mono text-emerald-400">{{ layoutCounts.corridors }}</b>
        </div>
        <div class="col-span-2 px-2 py-1.5 rounded bg-slate-900/50 border border-slate-800 flex justify-between items-center">
          <span class="text-slate-400">Точки POI:</span>
          <b class="font-mono text-rose-400">{{ layoutCounts.pois }}</b>
        </div>
      </div>
    </div>

    <!-- Blueprint underlay (Чертёж-подложка) -->
    <div class="px-4 py-3 border-b" style="border-color: var(--border)">
      <div class="flex items-center justify-between mb-2">
        <p class="text-xs font-medium uppercase tracking-wider" style="color: var(--text-muted)">Чертёж-подложка</p>
        <button
          v-if="currentFloor?.plan_url || currentFloor?.plan_image_url"
          @click="$emit('delete-plan')"
          class="text-xs text-rose-400 hover:text-rose-300 flex items-center gap-1 transition-colors cursor-pointer"
          title="Удалить загруженный чертёж этажа"
        >
          <Trash2 :size="12" /> Удалить
        </button>
      </div>

      <div class="space-y-2">
        <button
          id="upload-plan-btn"
          @click="$emit('upload-plan')"
          :disabled="!currentFloor"
          class="btn btn-ghost w-full justify-start text-xs gap-2.5"
        >
          <Upload :size="14" />
          {{ (currentFloor?.plan_url || currentFloor?.plan_image_url) ? 'Заменить чертёж' : 'Загрузить чертёж' }}
        </button>

        <div v-if="currentFloor?.plan_url || currentFloor?.plan_image_url" class="space-y-1.5 pt-1">
          <div class="flex items-center justify-between text-xs text-slate-400">
            <span class="flex items-center gap-1.5"><Sliders :size="12" /> Прозрачность</span>
            <span class="font-mono text-slate-300">{{ Math.round(blueprintOpacity * 100) }}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            :value="blueprintOpacity"
            @input="$emit('update:blueprintOpacity', parseFloat($event.target.value))"
            class="w-full accent-blue-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg appearance-none"
          />

          <!-- Blueprint Rotation Controls -->
          <div class="space-y-1.5 pt-2 border-t border-slate-800/80">
            <div class="flex items-center justify-between text-xs text-slate-400">
              <span class="flex items-center gap-1.5"><RotateCw :size="12" /> Поворот чертежа</span>
              <span class="font-mono text-slate-300">{{ blueprintRotation }}°</span>
            </div>
            <div class="grid grid-cols-2 gap-1.5">
              <button
                type="button"
                @click="$emit('rotate-plan', -90)"
                class="btn btn-ghost text-xs py-1 px-2 flex items-center justify-center gap-1 border border-slate-700/60 hover:bg-slate-800"
                title="Повернуть чертеж на 90° против часовой стрелки"
              >
                <RotateCcw :size="13" /> -90°
              </button>
              <button
                type="button"
                @click="$emit('rotate-plan', 90)"
                class="btn btn-ghost text-xs py-1 px-2 flex items-center justify-center gap-1 border border-slate-700/60 hover:bg-slate-800"
                title="Повернуть чертеж на 90° по часовой стрелке"
              >
                <RotateCw :size="13" /> +90°
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Scale Calibration (PPM) -->
    <div class="px-4 py-3">
      <p class="text-xs font-medium uppercase tracking-wider mb-2" style="color: var(--text-muted)">Масштаб (PPM)</p>

      <div v-if="!calibrating && !calibResult">
        <button
          id="start-calib-btn"
          @click="$emit('start-calib')"
          :disabled="!currentFloor"
          class="btn btn-ghost w-full justify-start text-xs gap-2.5 disabled:opacity-40"
        >
          <Ruler :size="14" />
          Задать масштаб
        </button>
        <p v-if="currentFloor?.ppm || currentFloor?.pixels_per_meter" class="text-xs mt-2" style="color: var(--text-muted)">
          Текущий: <b style="color: var(--text-secondary)">{{ (currentFloor.ppm ?? currentFloor.pixels_per_meter)?.toFixed(2) }} px/м</b>
        </p>
      </div>

      <div v-if="calibrating" class="p-3 rounded-lg text-sm" style="background: rgba(245,158,11,0.1); border: 1px solid rgba(245,158,11,0.25); color: #fbbf24">
        <p class="font-medium mb-1 text-xs">🎯 Режим калибровки</p>
        <p class="text-xs" style="color: #fcd34d">Кликните 2 точки на плане с известным расстоянием</p>
        <button @click="$emit('cancel-calib')" class="btn btn-ghost text-xs mt-2 py-1 w-full justify-center">Отмена</button>
      </div>

      <div v-if="calibResult && !calibrating" class="p-3 rounded-lg space-y-2" style="background: var(--bg-surface)">
        <p class="text-xs" style="color: var(--text-muted)">Расстояние: <b style="color:var(--text-secondary)">{{ calibResult.pixels.toFixed(1) }} px</b></p>
        <label class="label text-xs">Реальное расстояние (м)</label>
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
