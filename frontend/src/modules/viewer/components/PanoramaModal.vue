<script setup lang="ts">
import { ref } from 'vue'
import { X, Rotate3d, Compass, Eye } from 'lucide-vue-next'
import type { POI } from '../types'

interface Props {
  poi: POI | null
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const isDragging = ref(false)
const panX = ref(0)
const startX = ref(0)

function onMouseDown(e: MouseEvent) {
  isDragging.value = true
  startX.value = e.clientX - panX.value
}

function onMouseMove(e: MouseEvent) {
  if (!isDragging.value) return
  panX.value = e.clientX - startX.value
}

function onMouseUp() {
  isDragging.value = false
}

function onTouchStart(e: TouchEvent) {
  if (!e.touches[0]) return
  isDragging.value = true
  startX.value = e.touches[0].clientX - panX.value
}

function onTouchMove(e: TouchEvent) {
  if (!isDragging.value || !e.touches[0]) return
  panX.value = e.touches[0].clientX - startX.value
}

function onTouchEnd() {
  isDragging.value = false
}
</script>

<template>
  <div
    v-if="poi"
    class="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 pointer-events-auto"
    @click.self="emit('close')"
  >
    <div
      class="relative w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col"
    >
      <!-- Шапка модалки -->
      <div class="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/70">
        <div class="flex items-center gap-2.5">
          <div class="p-2 rounded-xl bg-purple-500/20 text-purple-400 border border-purple-500/30">
            <Rotate3d class="w-5 h-5" />
          </div>
          <div>
            <h3 class="text-base font-bold text-white">{{ poi.title }}</h3>
            <p class="text-xs text-slate-400">Виртуальный 360° тур (Pannellum Ready)</p>
          </div>
        </div>

        <button
          type="button"
          class="p-2 rounded-full text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          @click="emit('close')"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Область 360 панорамы (интерактивный drag-to-look) -->
      <div
        class="relative w-full h-80 sm:h-96 bg-slate-950 overflow-hidden cursor-grab active:cursor-grabbing select-none"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="onMouseUp"
        @mouseleave="onMouseUp"
        @touchstart="onTouchStart"
        @touchmove="onTouchMove"
        @touchend="onTouchEnd"
      >
        <!-- Имитация 360 панорамы холла с плавной прокруткой фона -->
        <div
          class="absolute inset-0 w-[300%] h-full bg-cover bg-center transition-transform duration-75"
          :style="{
            backgroundImage: `url('https://images.unsplash.com/photo-1517457373958-b7bdd4587205?auto=format&fit=crop&w=2000&q=80')`,
            transform: `translateX(${panX % 1000}px)`,
          }"
        ></div>

        <div class="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-black/30 pointer-events-none"></div>

        <!-- Центральный хотспот / маркер -->
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div class="flex flex-col items-center gap-2 animate-bounce">
            <div class="w-10 h-10 rounded-full bg-blue-600 border-2 border-white flex items-center justify-center shadow-lg shadow-blue-500/50">
              <Compass class="w-5 h-5 text-white animate-spin-slow" />
            </div>
            <span class="px-2.5 py-1 rounded-full bg-black/70 backdrop-blur-md text-xs font-semibold text-white border border-white/20">
              {{ poi.title }}
            </span>
          </div>
        </div>

        <!-- Подсказка управления -->
        <div class="absolute bottom-3 left-3 right-3 flex items-center justify-between text-xs text-slate-300 pointer-events-none bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-xl border border-white/10">
          <span class="flex items-center gap-1.5">
            <Eye class="w-3.5 h-3.5 text-blue-400" />
            Перетаскивайте пальцем или мышкой для обзора 360°
          </span>
          <span class="text-slate-400">ID: {{ poi.panorama_id || 'pano-default' }}</span>
        </div>
      </div>

      <!-- Описание локации внизу -->
      <div class="p-4 bg-slate-900 flex items-center justify-between gap-4">
        <p class="text-xs text-slate-300 line-clamp-2">
          {{ poi.description }}
        </p>
        <button
          type="button"
          class="shrink-0 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md transition-colors"
          @click="emit('close')"
        >
          Вернуться к карте
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes spinSlow {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
.animate-spin-slow {
  animation: spinSlow 12s linear infinite;
}
</style>
