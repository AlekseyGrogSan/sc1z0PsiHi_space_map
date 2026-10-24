<script setup lang="ts">
import { Layers } from 'lucide-vue-next'
import type { Floor } from '../types'

interface Props {
  floors: Floor[]
  activeFloorId: string
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'selectFloor', floor: Floor): void
}>()
</script>

<template>
  <aside
    class="flex flex-col items-center gap-1.5 p-1.5 rounded-2xl bg-slate-900/90 backdrop-blur-md border border-slate-800 shadow-xl shadow-black/40 pointer-events-auto"
    aria-label="Переключатель этажей"
  >
    <div class="p-1 text-slate-400 mb-0.5" title="Этажи здания">
      <Layers class="w-4 h-4" />
    </div>

    <!-- Список этажей (сверху вниз от верхнего к нижнему) -->
    <div class="flex flex-col gap-1.5">
      <button
        v-for="floor in [...floors].sort((a, b) => b.number - a.number)"
        :key="floor.id"
        type="button"
        class="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-sm transition-all cursor-pointer select-none"
        :class="[
          floor.id === activeFloorId
            ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30 ring-2 ring-blue-400 scale-105'
            : 'text-slate-300 hover:text-white hover:bg-slate-800/80',
        ]"
        :title="floor.title"
        @click="emit('selectFloor', floor)"
      >
        {{ floor.number }}
      </button>
    </div>
  </aside>
</template>
