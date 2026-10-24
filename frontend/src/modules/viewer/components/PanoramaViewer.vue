<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import {
  Rotate3d,
  Compass,
  ZoomIn,
  ZoomOut,
  RefreshCw,
  Loader2,
  AlertTriangle,
  MapPin,
  Smartphone,
} from 'lucide-vue-next'
import type { POI } from '../types'

export interface HotSpotItem {
  pitch: number
  yaw: number
  type?: 'scene' | 'info'
  text?: string
  title?: string
  target_panorama_id?: string
  sceneId?: string
  URL?: string
  id?: string | number
  cssClass?: string
  [key: string]: any
}

interface Props {
  panoramaUrl?: string | null
  imagePath?: string | null
  poi?: POI | null
  hotSpots?: HotSpotItem[]
  title?: string
  autoLoad?: boolean
  compass?: boolean
  yaw?: number
  pitch?: number
  hfov?: number
  showControls?: boolean
}

const props = withDefaults(defineProps<Props>() , {
  panoramaUrl: null,
  imagePath: null,
  poi: null,
  hotSpots: () => [],
  title: '',
  autoLoad: true,
  compass: false,
  yaw: 0,
  pitch: 0,
  hfov: 100,
  showControls: true,
})

const emit = defineEmits<{
  (e: 'hotspotClick', hotspot: HotSpotItem): void
  (e: 'load'): void
  (e: 'error', err: any): void
  (e: 'requestPoiSelection'): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)
let viewer: any = null

const isLoading = ref(false)
const hasError = ref(false)
const errorMessage = ref('')
const isOrientationActive = ref(false)

// Разрешение эффективного URL панорамы (MinIO, переданный путь, локальный демо-файл)
const effectivePanoramaUrl = computed(() => {
  if (props.panoramaUrl && props.panoramaUrl.trim()) {
    return props.panoramaUrl.trim()
  }
  if (props.imagePath && props.imagePath.trim()) {
    return props.imagePath.trim()
  }
  if (props.poi?.panorama_id) {
    const pId = props.poi.panorama_id.trim()
    if (pId.startsWith('http://') || pId.startsWith('https://') || pId.startsWith('/')) {
      return pId
    }
    // Для демо и моковых ID используем эквидистантную панораму холла из демо-ассетов
    return '/hall_360_panorama.jpg'
  }
  return null
})

// Название текущей точки
const displayTitle = computed(() => {
  return props.title || props.poi?.title || '360° Виртуальный тур'
})

// Уничтожение инстанса Pannellum
function destroyViewer() {
  if (viewer) {
    try {
      viewer.destroy()
    } catch (err) {
      console.warn('[Pannellum] destroy warning:', err)
    }
    viewer = null
  }
  if (containerRef.value) {
    containerRef.value.innerHTML = ''
    containerRef.value.classList.remove('pnlm-container')
  }
  isOrientationActive.value = false
}

// Преобразование хотспотов под формат Pannellum
function getFormattedHotspots() {
  if (!Array.isArray(props.hotSpots)) return []
  return props.hotSpots.map((hs, idx) => {
    const isScene = Boolean(hs.type === 'scene' || hs.target_panorama_id || hs.sceneId)
    return {
      id: hs.id ? String(hs.id) : `hs-${idx}`,
      pitch: Number(hs.pitch ?? 0),
      yaw: Number(hs.yaw ?? 0),
      type: isScene ? 'scene' : (hs.type || 'info'),
      text: hs.text || hs.title || 'Перейти к следующей панораме',
      sceneId: hs.sceneId || hs.target_panorama_id,
      URL: hs.URL,
      clickHandlerFunc: (_evt: any, args: any) => {
        emit('hotspotClick', args)
      },
      clickHandlerArgs: hs,
    }
  })
}

// Инициализация WebGL 3D-сферы Pannellum
function initPannellum() {
  destroyViewer()

  const url = effectivePanoramaUrl.value
  if (!url || !containerRef.value) {
    return
  }

  const pannellumLib = (window as any).pannellum
  if (!pannellumLib || typeof pannellumLib.viewer !== 'function') {
    console.error('[Pannellum] Библиотека window.pannellum не обнаружена.')
    hasError.value = true
    errorMessage.value = 'Ошибка загрузки движка Pannellum'
    return
  }

  isLoading.value = true
  hasError.value = false
  errorMessage.value = ''

  try {
    const config: any = {
      type: 'equirectangular',
      panorama: url,
      autoLoad: props.autoLoad,
      // Свободный круговой обзор на 360° без упора в границы по горизонтали
      minYaw: -180,
      maxYaw: 180,
      minPitch: -90,
      maxPitch: 90,
      yaw: props.yaw,
      pitch: props.pitch,
      hfov: props.hfov,
      minHfov: 40,
      maxHfov: 130,
      friction: 0.15,
      draggable: true,
      mouseZoom: true,
      keyboardZoom: true,
      showControls: false,
      showZoomCtrl: false,
      showFullscreenCtrl: false,
      compass: props.compass,
      crossOrigin: 'anonymous',
      hotSpots: getFormattedHotspots(),
    }

    viewer = pannellumLib.viewer(containerRef.value, config)

    viewer.on('load', () => {
      isLoading.value = false
      hasError.value = false
      emit('load')
      if (viewer && typeof viewer.resize === 'function') {
        viewer.resize()
      }
    })

    viewer.on('error', (err: any) => {
      console.warn('[Pannellum] Error event:', err)
      isLoading.value = false
      hasError.value = true
      errorMessage.value = typeof err === 'string' ? err : 'Не удалось загрузить панораму'
      emit('error', err)
    })
  } catch (err: any) {
    console.error('[Pannellum] Исключение при инициализации:', err)
    isLoading.value = false
    hasError.value = true
    errorMessage.value = err?.message || 'Ошибка инициализации 3D сферы'
    emit('error', err)
  }
}

// Управление зумом и положением
function handleZoomIn() {
  if (!viewer) return
  const cur = viewer.getHfov()
  viewer.setHfov(Math.max(40, cur - 15))
}

function handleZoomOut() {
  if (!viewer) return
  const cur = viewer.getHfov()
  viewer.setHfov(Math.min(130, cur + 15))
}

function handleResetView() {
  if (!viewer) return
  viewer.lookAt(0, 0, 100, 600)
}

function handleToggleOrientation() {
  if (!viewer) return
  try {
    if (isOrientationActive.value) {
      if (typeof viewer.stopOrientation === 'function') {
        viewer.stopOrientation()
      }
      isOrientationActive.value = false
    } else {
      if (typeof viewer.startOrientation === 'function') {
        viewer.startOrientation()
      }
      isOrientationActive.value = true
    }
  } catch (e) {
    console.warn('[Pannellum] Gyroscope toggle error:', e)
  }
}

function handleResize() {
  if (viewer && typeof viewer.resize === 'function') {
    viewer.resize()
  }
}

// Отслеживание смены URL или точки на 2D-карте
watch(
  () => effectivePanoramaUrl.value,
  (newUrl, oldUrl) => {
    if (newUrl !== oldUrl) {
      nextTick(() => {
        initPannellum()
      })
    }
  }
)

// Отслеживание смены хотспотов
watch(
  () => props.hotSpots,
  () => {
    if (effectivePanoramaUrl.value) {
      nextTick(() => {
        initPannellum()
      })
    }
  },
  { deep: true }
)

onMounted(() => {
  window.addEventListener('resize', handleResize)
  if (effectivePanoramaUrl.value) {
    nextTick(() => {
      initPannellum()
    })
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  destroyViewer()
})

defineExpose({
  destroy: destroyViewer,
  init: initPannellum,
  getViewer: () => viewer,
})
</script>

<template>
  <div class="panorama-viewer-root relative w-full h-full min-h-[360px] bg-slate-950 overflow-hidden select-none">
    <!-- WebGL Canvas Контейнер Pannellum -->
    <div
      ref="containerRef"
      class="pannellum-stage absolute inset-0 w-full h-full cursor-grab active:cursor-grabbing"
    ></div>

    <!-- ПЛАШКА-ЗАГЛУШКА: Точка на карте еще не выбрана -->
    <div
      v-if="!effectivePanoramaUrl"
      class="absolute inset-0 z-30 flex flex-col items-center justify-center p-6 text-center bg-slate-950/90 backdrop-blur-md"
    >
      <div class="w-16 h-16 rounded-2xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-blue-400 mb-4 shadow-xl shadow-blue-500/10">
        <Rotate3d class="w-8 h-8 animate-pulse text-blue-400" />
      </div>
      <h3 class="text-base sm:text-lg font-bold text-white mb-2">
        Выберите точку или помещение на карте, чтобы открыть 360° тур
      </h3>
      <p class="text-xs sm:text-sm text-slate-400 max-w-sm mb-5 leading-relaxed">
        Нажмите на маркер стенда, сцены или локации на 2D-плане помещения для мгновенного погружения в круговую панораму.
      </p>
      <button
        type="button"
        class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-lg shadow-blue-600/30 transition-all cursor-pointer"
        @click="emit('requestPoiSelection')"
      >
        <MapPin class="w-4 h-4" />
        <span>Выбрать на карте</span>
      </button>
    </div>

    <!-- Индикатор загрузки панорамы -->
    <div
      v-else-if="isLoading"
      class="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-slate-950/70 backdrop-blur-sm pointer-events-none"
    >
      <Loader2 class="w-9 h-9 text-blue-500 animate-spin" />
      <span class="text-xs font-medium text-slate-200">Загрузка 3D-сферы панорамы...</span>
    </div>

    <!-- Индикатор ошибки -->
    <div
      v-else-if="hasError"
      class="absolute inset-0 z-20 flex flex-col items-center justify-center p-6 text-center bg-slate-950/90 gap-3"
    >
      <AlertTriangle class="w-10 h-10 text-amber-400" />
      <h4 class="text-sm font-bold text-white">Не удалось открыть панораму</h4>
      <p class="text-xs text-slate-400 max-w-xs">{{ errorMessage }}</p>
      <button
        type="button"
        class="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors"
        @click="initPannellum"
      >
        Повторить попытку
      </button>
    </div>

    <!-- ОВЕРЛЕЙ: Заголовок локации -->
    <div
      v-if="effectivePanoramaUrl"
      class="absolute top-4 left-4 z-10 bg-slate-900/80 backdrop-blur-md px-3.5 py-2 rounded-2xl border border-slate-700/60 shadow-lg pointer-events-none flex items-center gap-2 max-w-[80%]"
    >
      <div class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping"></div>
      <div class="w-2.5 h-2.5 rounded-full bg-emerald-500 -ml-4.5"></div>
      <span class="text-xs sm:text-sm font-bold text-white truncate">{{ displayTitle }}</span>
    </div>

    <!-- ОВЕРЛЕЙ: Кнопки управления (Зум, Сброс, Гироскоп) -->
    <div
      v-if="effectivePanoramaUrl && props.showControls"
      class="absolute bottom-4 right-4 z-10 flex flex-col gap-2"
    >
      <button
        type="button"
        title="Приблизить"
        class="w-9 h-9 rounded-xl bg-slate-900/85 hover:bg-slate-800 border border-slate-700/60 text-slate-200 hover:text-white flex items-center justify-center shadow-lg transition-all active:scale-95 cursor-pointer backdrop-blur-md"
        @click="handleZoomIn"
      >
        <ZoomIn class="w-4 h-4" />
      </button>

      <button
        type="button"
        title="Отдалить"
        class="w-9 h-9 rounded-xl bg-slate-900/85 hover:bg-slate-800 border border-slate-700/60 text-slate-200 hover:text-white flex items-center justify-center shadow-lg transition-all active:scale-95 cursor-pointer backdrop-blur-md"
        @click="handleZoomOut"
      >
        <ZoomOut class="w-4 h-4" />
      </button>

      <button
        type="button"
        title="Сбросить ракурс"
        class="w-9 h-9 rounded-xl bg-slate-900/85 hover:bg-slate-800 border border-slate-700/60 text-slate-200 hover:text-white flex items-center justify-center shadow-lg transition-all active:scale-95 cursor-pointer backdrop-blur-md"
        @click="handleResetView"
      >
        <RefreshCw class="w-4 h-4" />
      </button>

      <button
        type="button"
        title="Гироскоп / Ориентация"
        class="w-9 h-9 rounded-xl bg-slate-900/85 hover:bg-slate-800 border border-slate-700/60 flex items-center justify-center shadow-lg transition-all active:scale-95 cursor-pointer backdrop-blur-md"
        :class="isOrientationActive ? 'text-blue-400 border-blue-500/60 bg-blue-950/60' : 'text-slate-200 hover:text-white'"
        @click="handleToggleOrientation"
      >
        <Smartphone class="w-4 h-4" />
      </button>
    </div>

    <!-- ОВЕРЛЕЙ: Подсказка по управлению -->
    <div
      v-if="effectivePanoramaUrl && !isLoading && !hasError"
      class="absolute bottom-4 left-4 z-10 hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-black/60 backdrop-blur-md border border-white/10 text-[11px] text-slate-300 pointer-events-none"
    >
      <Compass class="w-3.5 h-3.5 text-blue-400" />
      <span>Тяните мышью для обзора 360° • Колесико для зума</span>
    </div>
  </div>
</template>

<style scoped>
.panorama-viewer-root {
  width: 100%;
  height: 100%;
  min-height: 360px;
  position: relative;
  overflow: hidden;
  background-color: #020617;
}

.pannellum-stage {
  width: 100%;
  height: 100%;
  min-height: 360px;
  position: absolute;
  inset: 0;
}

/* Фиксация высоты и адаптивности Pannellum */
:deep(.pnlm-container) {
  width: 100% !important;
  height: 100% !important;
  position: absolute !important;
  inset: 0 !important;
  background-color: #020617 !important;
  cursor: grab !important;
}

:deep(.pnlm-render-container) {
  width: 100% !important;
  height: 100% !important;
}

:deep(.pnlm-ui) {
  width: 100% !important;
  height: 100% !important;
  position: absolute !important;
  inset: 0 !important;
  z-index: 1 !important;
}

/* Курсоры grab и grabbing при перетаскивании */
:deep(.pnlm-container),
:deep(.pnlm-grab),
:deep(.pnlm-ui),
:deep(.pnlm-dragfix) {
  cursor: grab !important;
}

:deep(.pnlm-container:active),
:deep(.pnlm-grabbing),
:deep(.pnlm-dragfix:active),
:deep(.pnlm-render-container:active) {
  cursor: grabbing !important;
}

/* Стилизация хотспотов Pannellum */
:deep(.pnlm-hotspot) {
  cursor: pointer !important;
  transition: transform 0.2s ease, filter 0.2s ease;
}

:deep(.pnlm-hotspot:hover) {
  transform: scale(1.2);
  filter: drop-shadow(0 0 10px rgba(59, 130, 246, 0.9));
}

:deep(div.pnlm-tooltip span) {
  background-color: rgba(15, 23, 42, 0.92) !important;
  border: 1px solid rgba(255, 255, 255, 0.15) !important;
  backdrop-filter: blur(8px) !important;
  color: #f8fafc !important;
  font-size: 12px !important;
  font-weight: 600 !important;
  padding: 6px 12px !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6) !important;
}
</style>
