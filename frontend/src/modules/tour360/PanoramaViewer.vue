<template>
  <div class="relative w-full h-[100dvh] bg-slate-950 text-white flex flex-col select-none overflow-hidden">
    <!-- Контейнер Pannellum 360 -->
    <div id="panorama" class="w-full h-full"></div>

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
import { Compass as CompassIcon, ArrowLeft } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()

const viewer = ref(null)
const isGyroActive = ref(false)

const pageTitle = computed(() => {
  return (route.query.title) || 'Выставка: Холл'
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/admin')
  }
}

onMounted(() => {
  if (typeof window !== 'undefined' && window.pannellum) {
    try {
      viewer.value = window.pannellum.viewer('panorama', {
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
        hotSpots: [
          {
            pitch: 14.1,
            yaw: 1.5,
            type: "info",
            text: "Стенд ТТК",
            URL: "#"
          },
          {
            pitch: -9.4,
            yaw: 222.6,
            type: "scene",
            text: "Переход в коридор",
            sceneId: "scene2"
          }
        ]
      })
    } catch (err) {
      console.warn("Ошибка инициализации Pannellum:", err)
    }
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