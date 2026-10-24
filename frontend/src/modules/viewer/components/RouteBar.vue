<script setup lang="ts">
import { computed } from 'vue'
import { Footprints, X, ArrowUpRight, Rotate3d, CornerDownRight, MapPin } from 'lucide-vue-next'
import type { RouteResponse } from '../types'

interface Props {
  route: RouteResponse | null
  targetPoiTitle?: string
  originTitle?: string
  isPickingOrigin?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'reset'): void
  (e: 'openVirtualTour'): void
  (e: 'pickOriginOnMap'): void
}>()

// Форматирование расстояния
const formattedDistance = computed(() => {
  if (!props.route) return ''
  const d = Math.round(props.route.total_distance_meters ?? props.route.distance_meters ?? 0)
  return `${d} м`
})

// Форматирование времени пешком
const formattedTime = computed(() => {
  if (!props.route) return ''
  const secs = props.route.estimated_time_seconds ?? props.route.estimated_seconds ?? 0
  if (secs < 60) return `~${secs} сек`
  const mins = Math.ceil(secs / 60)
  return `~${mins} мин пешком`
})

// Проверка наличия смены этажа
const floorChangeStep = computed(() => {
  if (!props.route?.steps) return null
  return props.route.steps.find((s) => s.target_floor !== undefined || s.kind === 'stairs' || s.kind === 'elevator')
})

// Текущая инструкция
const primaryInstruction = computed(() => {
  if (!props.route?.steps?.length) return 'Следуйте по синей линии'
  if (floorChangeStep.value) {
    return floorChangeStep.value.text || floorChangeStep.value.instruction || `Поднимитесь на ${floorChangeStep.value.target_floor} этаж`
  }
  const s = props.route.steps[0]
  return s.text || s.instruction || 'Следуйте по синей линии'
})
</script>

<template>
  <transition
    enter-active-class="transform transition ease-out duration-300"
    enter-from-class="translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transform transition ease-in duration-200"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="translate-y-full opacity-0"
  >
    <div
      v-if="route"
      class="w-full max-w-lg mx-auto bg-slate-900/95 backdrop-blur-xl border border-blue-500/40 rounded-3xl p-4 shadow-2xl shadow-blue-950/40 pointer-events-auto flex flex-col gap-3 text-slate-100 ring-1 ring-blue-500/20"
    >
      <!-- Верхняя строка: Иконка, Дистанция, Время и Кнопка сброса -->
      <div class="flex items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-2xl bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400 shrink-0">
            <Footprints class="w-5 h-5" />
          </div>

          <div>
            <div class="flex items-center gap-2">
              <span class="text-base font-bold text-white">{{ formattedDistance }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full bg-blue-600/20 text-blue-300 font-medium border border-blue-500/30">
                {{ formattedTime }}
              </span>
            </div>
            <div class="text-[11px] text-slate-400">
              Оптимальный маршрут без препятствий
            </div>
          </div>
        </div>

        <button
          type="button"
          class="p-2 rounded-xl bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors cursor-pointer"
          title="Сбросить маршрут"
          @click="emit('reset')"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Адреса: Откуда и Куда с возможностью выбора старта на карте -->
      <div class="flex flex-col gap-1.5 p-2.5 rounded-2xl bg-slate-950/60 border border-slate-800/80 text-xs">
        <!-- Откуда -->
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0 flex-1">
            <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 shrink-0 shadow-sm shadow-emerald-400"></span>
            <span class="text-slate-400 shrink-0">Откуда:</span>
            <span class="text-slate-100 font-semibold truncate">{{ originTitle || 'Точка отправления' }}</span>
          </div>
          <button
            type="button"
            @click="emit('pickOriginOnMap')"
            class="px-2 py-0.5 rounded-lg text-[11px] font-medium transition-all shrink-0 cursor-pointer flex items-center gap-1"
            :class="isPickingOrigin
              ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 ring-1 ring-emerald-400'
              : 'bg-slate-800 hover:bg-slate-700 text-blue-300 border border-slate-700'"
          >
            <MapPin class="w-3 h-3" />
            <span>{{ isPickingOrigin ? 'Кликните на карту...' : 'Выбрать на карте' }}</span>
          </button>
        </div>

        <div class="border-t border-slate-800/50 my-0.5"></div>

        <!-- Куда -->
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-2 min-w-0 flex-1">
            <span class="w-2.5 h-2.5 rounded-full bg-rose-500 shrink-0 shadow-sm shadow-rose-500"></span>
            <span class="text-slate-400 shrink-0">Куда:</span>
            <span class="text-slate-100 font-semibold truncate">{{ targetPoiTitle || 'Точка назначения' }}</span>
          </div>
        </div>
      </div>

      <!-- Подсказка / Шаг навигации -->
      <div
        class="flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium"
        :class="[
          floorChangeStep
            ? 'bg-amber-500/10 border border-amber-500/30 text-amber-300'
            : 'bg-slate-800/80 border border-slate-700/60 text-slate-200',
        ]"
      >
        <component
          :is="floorChangeStep ? ArrowUpRight : CornerDownRight"
          class="w-4 h-4 shrink-0"
          :class="floorChangeStep ? 'text-amber-400' : 'text-blue-400'"
        />
        <span class="flex-1">{{ primaryInstruction }}</span>
      </div>

      <!-- Дополнительная кнопка виртуального тура по маршруту -->
      <button
        type="button"
        class="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-xl bg-slate-800/80 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition-all cursor-pointer"
        @click="emit('openVirtualTour')"
      >
        <Rotate3d class="w-4 h-4 text-purple-400" />
        <span>Пройти маршрут виртуально (360°)</span>
      </button>
    </div>
  </transition>
</template>
