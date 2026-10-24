<script setup lang="ts">
import { computed } from 'vue'
import { X, Rotate3d, Maximize2, Minimize2, MapPin } from 'lucide-vue-next'
import type { POI } from '../types'
import PanoramaViewer, { type HotSpotItem } from './PanoramaViewer.vue'

interface Props {
  poi?: POI | null
  panoramaUrl?: string | null
  imagePath?: string | null
  hotSpots?: HotSpotItem[]
  allPois?: POI[]
}

const props = withDefaults(defineProps<Props>(), {
  poi: null,
  panoramaUrl: null,
  imagePath: null,
  hotSpots: () => [],
  allPois: () => [],
})

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'selectHotspot', hotspot: HotSpotItem): void
  (e: 'selectPoi', poi: POI): void
}>()

// Вычисляем хотспоты перехода: либо переданные извне, либо контекстные для демо
const effectiveHotSpots = computed<HotSpotItem[]>(() => {
  if (props.hotSpots && props.hotSpots.length > 0) {
    return props.hotSpots
  }

  // Если открыт конкретный стенд в демо, создаем навигационные переходы между залами
  const pId = props.poi?.panorama_id
  if (pId === 'pano-stand-ttk') {
    return [
      {
        id: 'hs-to-ai',
        pitch: -2,
        yaw: 55,
        type: 'scene',
        title: 'Стенд AI & Robotics',
        text: 'Переход: Стенд AI & Robotics',
        target_panorama_id: 'poi-stand-ai',
      },
      {
        id: 'hs-to-stage',
        pitch: 1,
        yaw: -70,
        type: 'scene',
        title: 'Главная сцена',
        text: 'Переход: Главная сцена (Main Stage)',
        target_panorama_id: 'poi-main-stage',
      },
      {
        id: 'hs-to-entrance',
        pitch: -5,
        yaw: 175,
        type: 'scene',
        title: 'Вход на выставку',
        text: 'Переход: Центральный вход',
        target_panorama_id: 'poi-entrance',
      },
    ]
  }

  if (pId === 'pano-stand-ai') {
    return [
      {
        id: 'hs-to-ttk',
        pitch: -2,
        yaw: -125,
        type: 'scene',
        title: 'Главный стенд ТТК',
        text: 'Переход: Главный стенд ТТК',
        target_panorama_id: 'poi-stand-ttk',
      },
      {
        id: 'hs-to-stage',
        pitch: 0,
        yaw: 80,
        type: 'scene',
        title: 'Главная сцена',
        text: 'Переход: Главная сцена',
        target_panorama_id: 'poi-main-stage',
      },
    ]
  }

  if (pId === 'pano-main-stage') {
    return [
      {
        id: 'hs-to-ttk',
        pitch: -1,
        yaw: 110,
        type: 'scene',
        title: 'Главный стенд ТТК',
        text: 'Переход: Главный стенд ТТК',
        target_panorama_id: 'poi-stand-ttk',
      },
      {
        id: 'hs-to-conf',
        pitch: 0,
        yaw: -85,
        type: 'scene',
        title: 'Зал Восток',
        text: 'Переход: Конференц-зал Восток',
        target_panorama_id: 'poi-conf-vostok',
      },
    ]
  }

  if (pId === 'pano-entrance') {
    return [
      {
        id: 'hs-to-ttk',
        pitch: -1,
        yaw: 10,
        type: 'scene',
        title: 'Главный стенд ТТК',
        text: 'Переход: Главный стенд ТТК',
        target_panorama_id: 'poi-stand-ttk',
      },
    ]
  }

  return []
})

// Обработка перехода по хотспоту
function handleHotspotClick(hotspot: HotSpotItem) {
  emit('selectHotspot', hotspot)

  const targetId = hotspot.target_panorama_id || hotspot.sceneId
  if (targetId && props.allPois.length > 0) {
    const nextPoi = props.allPois.find(
      (p) => p.id === targetId || p.panorama_id === targetId
    )
    if (nextPoi) {
      emit('selectPoi', nextPoi)
    }
  }
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 pointer-events-auto"
    @click.self="emit('close')"
  >
    <div
      class="relative w-full max-w-5xl h-[88vh] sm:h-[82vh] min-h-[500px] bg-slate-900 border border-slate-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col"
    >
      <!-- Шапка модалки -->
      <div class="flex items-center justify-between px-5 py-3.5 border-b border-slate-800 bg-slate-950/80 shrink-0">
        <div class="flex items-center gap-3">
          <div class="p-2.5 rounded-xl bg-purple-500/20 text-purple-400 border border-purple-500/30 shadow-md">
            <Rotate3d class="w-5 h-5" />
          </div>
          <div>
            <h3 class="text-base font-bold text-white leading-tight">
              {{ poi ? poi.title : '360° Виртуальный тур' }}
            </h3>
            <p class="text-xs text-slate-400">
              Pannellum WebGL 3D-сфера • 360° круговой обзор
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <button
            type="button"
            title="Закрыть тур"
            class="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
            @click="emit('close')"
          >
            <X class="w-5 h-5" />
          </button>
        </div>
      </div>

      <!-- Область 360 панорамы (Pannellum WebGL 3D Сфера) -->
      <div class="relative w-full flex-1 min-h-[360px] bg-slate-950 overflow-hidden">
        <PanoramaViewer
          :panorama-url="props.panoramaUrl"
          :image-path="props.imagePath"
          :poi="props.poi"
          :hot-spots="effectiveHotSpots"
          :title="props.poi?.title"
          :auto-load="true"
          :compass="true"
          @hotspot-click="handleHotspotClick"
          @request-poi-selection="emit('close')"
        />
      </div>

      <!-- Подвал модалки: описание локации и быстрый возврат к 2D-карте -->
      <div class="px-5 py-3.5 bg-slate-900/90 border-t border-slate-800 flex items-center justify-between gap-4 shrink-0">
        <div class="min-w-0">
          <p v-if="poi?.description" class="text-xs text-slate-300 line-clamp-1">
            {{ poi.description }}
          </p>
          <p v-else class="text-xs text-slate-400">
            Перетаскивайте изображение мышкой или пальцем для свободного обзора на 360 градусов.
          </p>
          <div class="flex items-center gap-2 mt-0.5">
            <span class="text-[11px] text-slate-500">
              ID панорамы: {{ poi?.panorama_id || props.panoramaUrl || 'не выбрано' }}
            </span>
            <span v-if="effectiveHotSpots.length > 0" class="text-[11px] text-blue-400 font-medium">
              • Доступно переходов (хотспотов): {{ effectiveHotSpots.length }}
            </span>
          </div>
        </div>

        <button
          type="button"
          class="shrink-0 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-md shadow-blue-600/25 transition-all cursor-pointer"
          @click="emit('close')"
        >
          Вернуться к карте
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Дополнительные стили модального окна */
</style>
