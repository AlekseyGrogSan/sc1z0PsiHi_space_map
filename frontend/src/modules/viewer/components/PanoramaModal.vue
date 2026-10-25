<script setup lang="ts">
import { ref, watch, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { X, Rotate3d, Compass, Eye, Maximize2 } from 'lucide-vue-next'
import type { POI } from '../types'

interface Props {
  poi: POI | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const router = useRouter()
const viewer = ref<any>(null)
const hasPannellum = ref(false)
const isGyroActive = ref(false)

// Fallback drag state if Pannellum fails to load
const isDragging = ref(false)
const panX = ref(0)
const startX = ref(0)

const isLoadingPannellum = ref(true)
const loadError = ref(false)
let watchdogTimer: any = null

function initPannellum() {
  if (watchdogTimer) {
    clearTimeout(watchdogTimer)
    watchdogTimer = null
  }
  loadError.value = false
  isLoadingPannellum.value = true

  if (!props.poi?.panorama_id) {
    hasPannellum.value = false
    isLoadingPannellum.value = false
    return
  }

  if (viewer.value) {
    try {
      viewer.value.destroy()
    } catch {
      // ignore
    }
    viewer.value = null
  }

  nextTick(() => {
    if (typeof window !== 'undefined' && (window as any).pannellum) {
      const container = document.getElementById('modal-panorama-container')
      if (container) {
        try {
          viewer.value = (window as any).pannellum.viewer('modal-panorama-container', {
            type: 'cubemap',
            cubemap: [
              '/cubemap/l1/f_0_0.webp',
              '/cubemap/l1/r_0_0.webp',
              '/cubemap/l1/b_0_0.webp',
              '/cubemap/l1/l_0_0.webp',
              '/cubemap/l1/u_0_0.webp',
              '/cubemap/l1/d_0_0.webp'
            ],
            autoLoad: true,
            compass: true,
            showControls: true,
            title: props.poi?.title || 'Панорама 360°'
          })

          if (viewer.value && typeof viewer.value.on === 'function') {
            viewer.value.on('load', () => {
              isLoadingPannellum.value = false
              hasPannellum.value = true
              if (watchdogTimer) {
                clearTimeout(watchdogTimer)
                watchdogTimer = null
              }
            })

            viewer.value.on('error', (err: any) => {
              console.warn('Pannellum error, switching to interactive fallback:', err)
              isLoadingPannellum.value = false
              hasPannellum.value = false
              loadError.value = true
              if (watchdogTimer) {
                clearTimeout(watchdogTimer)
                watchdogTimer = null
              }
            })
          }

          // Watchdog timer: fallback after 3.5s if Pannellum hangs on missing tiles
          watchdogTimer = setTimeout(() => {
            if (isLoadingPannellum.value) {
              console.warn('Pannellum load timed out, switching to interactive fallback')
              isLoadingPannellum.value = false
              hasPannellum.value = false
              loadError.value = true
            }
          }, 3500)

          hasPannellum.value = true
        } catch (e) {
          console.warn('Pannellum modal init failed, using fallback:', e)
          hasPannellum.value = false
          isLoadingPannellum.value = false
          loadError.value = true
        }
      }
    } else {
      hasPannellum.value = false
      isLoadingPannellum.value = false
    }
  })
}

watch(
  () => props.poi,
  (newPoi) => {
    if (newPoi) {
      initPannellum()
    } else {
      if (viewer.value) {
        try {
          viewer.value.destroy()
        } catch {
          // ignore
        }
        viewer.value = null
      }
    }
  },
  { immediate: true }
)

const toggleGyroscope = async () => {
  if (
    typeof DeviceOrientationEvent !== 'undefined' &&
    typeof (DeviceOrientationEvent as any).requestPermission === 'function'
  ) {
    try {
      const response = await (DeviceOrientationEvent as any).requestPermission()
      if (response !== 'granted') {
        alert('Доступ к гироскопу отклонён')
        return
      }
    } catch (e) {
      console.error(e)
    }
  }

  if (viewer.value && typeof viewer.value.toggleOrientation === 'function') {
    viewer.value.toggleOrientation()
    isGyroActive.value = !isGyroActive.value
  }
}

function openFullTour() {
  const title = props.poi ? encodeURIComponent(props.poi.title) : ''
  emit('close')
  router.push(`/tour360?title=${title}`)
}

function onMouseDown(e: MouseEvent) {
  if (hasPannellum.value) return
  isDragging.value = true
  startX.value = e.clientX - panX.value
}

function onMouseMove(e: MouseEvent) {
  if (hasPannellum.value || !isDragging.value) return
  panX.value = e.clientX - startX.value
}

function onMouseUp() {
  isDragging.value = false
}

function onTouchStart(e: TouchEvent) {
  if (hasPannellum.value || !e.touches[0]) return
  isDragging.value = true
  startX.value = e.touches[0].clientX - panX.value
}

function onTouchMove(e: TouchEvent) {
  if (hasPannellum.value || !isDragging.value || !e.touches[0]) return
  panX.value = e.touches[0].clientX - startX.value
}

function onTouchEnd() {
  isDragging.value = false
}

onBeforeUnmount(() => {
  if (watchdogTimer) {
    clearTimeout(watchdogTimer)
    watchdogTimer = null
  }
  if (viewer.value) {
    try {
      viewer.value.destroy()
    } catch {
      // ignore
    }
    viewer.value = null
  }
})
</script>

<template>
  <div
    v-if="poi"
    class="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-3 sm:p-4 pointer-events-auto"
    @click.self="emit('close')"
  >
    <div
      class="relative w-full max-w-2xl bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col"
    >
      <!-- Шапка модалки -->
      <div class="flex items-center justify-between p-3.5 sm:p-4 border-b border-slate-800 bg-slate-950/70">
        <div class="flex items-center gap-2.5">
          <div class="p-2 rounded-xl bg-purple-500/20 text-purple-400 border border-purple-500/30">
            <Rotate3d class="w-5 h-5" />
          </div>
          <div>
            <h3 class="text-sm sm:text-base font-bold text-white">{{ poi.title }}</h3>
            <p class="text-[11px] sm:text-xs text-slate-400">Виртуальный 360° тур (Pannellum 3D)</p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            @click="openFullTour"
            class="p-2 rounded-xl text-blue-400 hover:text-white hover:bg-slate-800 transition-colors flex items-center gap-1 text-xs"
            title="Открыть на весь экран"
          >
            <Maximize2 class="w-4 h-4" />
            <span class="hidden sm:inline">Полный тур</span>
          </button>
          <button
            type="button"
            class="p-2 rounded-full text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            @click="emit('close')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
      </div>

      <!-- Область 360 панорамы -->
      <div
        class="relative w-full h-80 sm:h-96 bg-slate-950 overflow-hidden select-none"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="onMouseUp"
        @mouseleave="onMouseUp"
        @touchstart="onTouchStart"
        @touchmove="onTouchMove"
        @touchend="onTouchEnd"
      >
        <!-- Реальный контейнер Pannellum -->
        <div id="modal-panorama-container" class="w-full h-full"></div>

        <!-- Имитация (если Pannellum оффлайн или не поддерживается) -->
        <div
          v-if="!hasPannellum"
          class="absolute inset-0 w-[300%] h-full bg-cover bg-center transition-transform duration-75 cursor-grab active:cursor-grabbing"
          :style="{
            backgroundImage: `url('https://images.unsplash.com/photo-1517457373958-b7bdd4587205?auto=format&fit=crop&w=2000&q=80')`,
            transform: `translateX(${panX % 1000}px)`,
          }"
        ></div>

        <!-- Уведомление об интерактивном режиме при сбое кубической панорамы -->
        <div
          v-if="loadError"
          class="absolute top-3 left-3 right-3 flex items-center gap-2 text-[11px] text-amber-200 bg-slate-950/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-amber-500/40 shadow-lg pointer-events-none z-10"
        >
          <span>ℹ️ Панорамные тайлы загружаются. Включен интерактивный обзор 360°.</span>
        </div>

        <!-- Кнопка гироскопа в углу панорамы -->
        <button
          v-if="hasPannellum"
          type="button"
          @click="toggleGyroscope"
          title="Включить / выключить гироскоп"
          :class="[
            'absolute bottom-3 right-3 p-2.5 rounded-full shadow-lg border transition-all z-10 flex items-center justify-center',
            isGyroActive
              ? 'bg-blue-600 text-white border-blue-400 ring-2 ring-blue-500/50'
              : 'bg-slate-900/90 text-blue-400 hover:text-white hover:bg-slate-800 border-slate-700/60'
          ]"
        >
          <Compass class="w-5 h-5 animate-pulse" v-if="isGyroActive" />
          <Compass class="w-5 h-5" v-else />
        </button>

        <!-- Подсказка управления -->
        <div
          class="absolute bottom-3 left-3 right-16 flex items-center justify-between text-xs text-slate-300 pointer-events-none bg-black/60 backdrop-blur-md px-3 py-1.5 rounded-xl border border-white/10"
        >
          <span class="flex items-center gap-1.5 truncate">
            <Eye class="w-3.5 h-3.5 text-blue-400 shrink-0" />
            Вращайте пальцем или мышкой для 360° обзора
          </span>
        </div>
      </div>

      <!-- Описание локации внизу -->
      <div class="p-3.5 sm:p-4 bg-slate-900 flex items-center justify-between gap-3 sm:gap-4 border-t border-slate-800">
        <p class="text-xs text-slate-300 line-clamp-2">
          {{ poi.description || 'Панорамный 360° снимок точки на плане этажа' }}
        </p>
        <div class="flex items-center gap-2 shrink-0">
          <button
            type="button"
            class="px-3.5 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md transition-colors"
            @click="openFullTour"
          >
            Тур 360°
          </button>
          <button
            type="button"
            class="px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold transition-colors"
            @click="emit('close')"
          >
            К карте
          </button>
        </div>
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
