<template>
  <div class="relative w-full h-[100dvh] bg-slate-950 text-white flex flex-col select-none overflow-hidden">
    <!-- Контейнер Pannellum 360 -->
    <div id="panorama" class="w-full h-full"></div>

    <!-- Индикатор загрузки -->
    <div
      v-if="isLoading"
      class="absolute inset-0 z-30 flex flex-col items-center justify-center bg-slate-950/80 backdrop-blur-sm gap-3 pointer-events-none"
    >
      <Loader2 class="w-10 h-10 text-purple-400 animate-spin" />
      <span class="text-sm text-purple-300 font-medium">Загрузка 360° панорамы...</span>
    </div>

    <!-- Верхняя панель: кнопка назад и заголовок -->
    <div
      class="absolute top-4 left-4 right-4 flex items-center justify-between pointer-events-none z-20"
      style="padding-top: env(safe-area-inset-top, 0px);"
    >
      <div class="flex items-center gap-2 pointer-events-auto">
        <button
          type="button"
          @click="goBack"
          class="p-2.5 bg-slate-900/90 hover:bg-slate-800 text-white rounded-xl backdrop-blur-md shadow-lg border border-slate-700/50 transition-colors flex items-center gap-1.5 text-xs font-semibold"
        >
          <ArrowLeft class="w-4 h-4" />
          <span class="hidden sm:inline">Назад</span>
        </button>
        <div class="bg-slate-900/80 p-2.5 px-3.5 rounded-xl backdrop-blur-md border border-slate-700/50">
          <h2 class="text-sm sm:text-base font-bold text-white">{{ pageTitle }}</h2>
        </div>
      </div>

      <div class="pointer-events-auto flex items-center gap-2">
        <span class="text-xs text-slate-300 bg-slate-900/80 px-2.5 py-1.5 rounded-lg border border-slate-700/50 backdrop-blur-md hidden sm:inline-block">
          Обзор 360°
        </span>
      </div>
    </div>

    <!-- Кнопки управления внизу справа: Гироскоп -->
    <div
      class="absolute bottom-6 right-6 flex items-center gap-3 z-20 pointer-events-auto"
      style="padding-bottom: env(safe-area-inset-bottom, 0px);"
    >
      <button
        type="button"
        @click="toggleGyroscope"
        title="Включить / выключить гироскоп"
        :class="[
          'p-3.5 rounded-full shadow-xl transition-all duration-200 border flex items-center justify-center',
          isGyroActive
            ? 'bg-blue-600 text-white border-blue-400 ring-4 ring-blue-500/30'
            : 'bg-slate-900/90 hover:bg-slate-800 text-blue-400 border-slate-700/60'
        ]"
      >
        <CompassIcon class="w-6 h-6 animate-pulse" v-if="isGyroActive" />
        <CompassIcon class="w-6 h-6" v-else />
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Compass as CompassIcon, ArrowLeft, Loader2 } from 'lucide-vue-next'
import { panoramaApi } from '../../api'
import { resolveMediaUrl } from '../../api/client'

const router = useRouter()
const route = useRoute()

const viewer = ref(null)
const isGyroActive = ref(false)
const isLoading = ref(true)
const loadedTitle = ref('')

const pageTitle = computed(() => {
  return loadedTitle.value || route.query.title || '360° Тур'
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/admin')
  }
}

onMounted(async () => {
  const panoId = route.query.panoramaId || route.query.id
  let panoData = null

  if (panoId) {
    try {
      const res = await panoramaApi.getPanorama(panoId)
      panoData = res.data
      if (panoData?.title) {
        loadedTitle.value = panoData.title
      }
    } catch (err) {
      console.warn('Не удалось загрузить панораму:', err)
    }
  }

  // Wait for window.pannellum if still initializing
  let tries = 0
  while (typeof window !== 'undefined' && !window.pannellum && tries < 15) {
    await new Promise(r => setTimeout(r, 100))
    tries++
  }

  if (typeof window !== 'undefined' && window.pannellum) {
    try {
      let pannellumConfig = null

      if (panoData?.original_url || panoData?.original_key) {
        const originalPath = panoData.original_url || `/api/v1/media/public/${panoData.original_key}`
        pannellumConfig = {
          type: 'equirectangular',
          panorama: resolveMediaUrl(originalPath),
          autoLoad: true,
          compass: true,
          showControls: true,
          title: panoData.title || pageTitle.value,
        }
      } else if (panoData?.preview_url || panoData?.preview_key) {
        const previewPath = panoData.preview_url || `/api/v1/media/public/${panoData.preview_key}`
        pannellumConfig = {
          type: 'equirectangular',
          panorama: resolveMediaUrl(previewPath),
          autoLoad: true,
          compass: true,
          showControls: true,
          title: panoData.title || pageTitle.value,
        }
      } else if (panoData?.cubemap_prefix) {
        const prefix = resolveMediaUrl(`/api/v1/media/public/${panoData.cubemap_prefix}`)
        pannellumConfig = {
          type: 'cubemap',
          cubeMap: [
            `${prefix}/l1/f_0_0.webp`,
            `${prefix}/l1/r_0_0.webp`,
            `${prefix}/l1/b_0_0.webp`,
            `${prefix}/l1/l_0_0.webp`,
            `${prefix}/l1/u_0_0.webp`,
            `${prefix}/l1/d_0_0.webp`
          ],
          autoLoad: true,
          compass: true,
          showControls: true,
          title: panoData.title || pageTitle.value
        }
      } else {
        // Fallback static demo cubemap with CORRECT camelCase cubeMap
        pannellumConfig = {
          type: 'cubemap',
          cubeMap: [
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
          title: pageTitle.value,
          hotSpots: [
            {
              pitch: 14.1,
              yaw: 1.5,
              type: "info",
              text: "Точка обзора"
            }
          ]
        }
      }

      if (panoData?.initial_heading) {
        pannellumConfig.yaw = panoData.initial_heading
      }

      if (Array.isArray(panoData?.hotspots) && panoData.hotspots.length > 0) {
        pannellumConfig.hotSpots = panoData.hotspots.map((h) => ({
          pitch: h.pitch,
          yaw: h.yaw,
          type: 'info',
          text: h.title || 'Переход',
        }))
      }

      viewer.value = window.pannellum.viewer('panorama', pannellumConfig)

      if (viewer.value && typeof viewer.value.on === 'function') {
        viewer.value.on('load', () => {
          isLoading.value = false
        })
        viewer.value.on('error', (e) => {
          console.warn('Pannellum error:', e)
          isLoading.value = false
        })
      }

      // Safety timeout
      setTimeout(() => {
        isLoading.value = false
      }, 3000)

    } catch (err) {
      console.warn("Ошибка инициализации Pannellum:", err)
      isLoading.value = false
    }
  } else {
    isLoading.value = false
  }
})

const toggleGyroscope = async () => {
  if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
    try {
      const response = await DeviceOrientationEvent.requestPermission()
      if (response !== 'granted') {
        alert('Доступ к гироскопу отклонён')
        return
      }
    } catch (e) {
      console.error(e)
    }
  }

  if (viewer.value) {
    viewer.value.toggleOrientation()
    isGyroActive.value = !isGyroActive.value
  }
}

onBeforeUnmount(() => {
  if (viewer.value) {
    viewer.value.destroy()
    viewer.value = null
  }
})
</script>