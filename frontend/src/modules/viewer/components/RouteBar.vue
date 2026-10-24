<script setup lang="ts">
import { computed } from 'vue'
import { Footprints, X, ArrowUpRight, Rotate3d, CornerDownRight } from 'lucide-vue-next'
import type { RouteResponse } from '../types'

interface Props {
  route: RouteResponse | null
  targetPoiTitle?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'reset'): void
  (e: 'openVirtualTour'): void
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
            <div v-if="targetPoiTitle" class="text-xs text-slate-400 truncate max-w-56">
              Маршрут до: <span class="text-slate-200 font-medium">{{ targetPoiTitle }}</span>
            </div>
          </div>
        </div>

        <button
          type="button"
          class="p-2 rounded-xl bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
          title="Сбросить маршрут"
          @click="emit('reset')"
        >
          <X class="w-5 h-5" />
        </button>
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
