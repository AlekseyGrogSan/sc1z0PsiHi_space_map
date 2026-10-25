<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Loader2, AlertCircle, Layers, Sliders, X } from 'lucide-vue-next'
import { getSpaceBySlug, getRoute } from '../api'
import type { Space, Floor, POI, PoiCategory, RouteResponse, RoutePoint } from '../types'
import ViewerMap from '../components/ViewerMap.vue'
import ViewerSearch from '../components/ViewerSearch.vue'
import FloorSelector from '../components/FloorSelector.vue'
import PoiBottomSheet from '../components/PoiBottomSheet.vue'
import RouteBar from '../components/RouteBar.vue'
import PanoramaModal from '../components/PanoramaModal.vue'

interface Props {
  slug?: string
}

const props = defineProps<Props>()
const route = useRoute()

// Основное состояние пространства
const space = ref<Space | null>(null)
const isLoading = ref(true)
const errorMessage = ref<string | null>(null)

// Интерактивное состояние экрана
const activeFloor = ref<Floor | null>(null)
const selectedPoi = ref<POI | null>(null)
const searchQuery = ref('')
const selectedCategory = ref<PoiCategory | 'all'>('all')

// Состояние навигации и маршрута
const isRouting = ref(false)
const activeRoute = ref<RouteResponse | null>(null)
const routeOrigin = ref<(RoutePoint & { title?: string; poiId?: string }) | null>(null)
const routeTarget = ref<POI | null>(null)
const isPickingStartOnMap = ref(false)
const routeErrorMessage = ref<string | null>(null)

// Настройка прозрачности подложки для посетителей
const blueprintOpacity = ref(0.85)
const showOpacityMenu = ref(false)

// Модалка 360 панорамы
const isPanoramaOpen = ref(false)
const panoramaPoi = ref<POI | null>(null)

// Получение slug из props или route params
const currentSlug = computed(() => {
  return (props.slug || route.params.slug || 'ttk-conf-2026') as string
})

// Загрузка данных пространства при монтировании
async function loadSpaceData() {
  isLoading.value = true
  errorMessage.value = null

  try {
    const data = await getSpaceBySlug(currentSlug.value)
    space.value = data

    // Устанавливаем первый этаж по умолчанию
    if (data.floors && data.floors.length > 0) {
      activeFloor.value = data.floors[0]
    }
  } catch (err: any) {
    console.error('Ошибка загрузки пространства:', err)
    errorMessage.value = 'Не удалось загрузить данные площадки'
  } finally {
    isLoading.value = false
  }
}

// Фильтрованный список POI с учетом поиска и выбранной категории
const filteredPois = computed(() => {
  if (!space.value) return []
  return space.value.pois.filter((poi) => {
    // Фильтр по категории
    if (selectedCategory.value !== 'all' && poi.category !== selectedCategory.value) {
      return false
    }
    // Живой поиск по названию и описанию
    if (searchQuery.value.trim()) {
      const q = searchQuery.value.trim().toLowerCase()
      const matchesTitle = poi.title.toLowerCase().includes(q)
      const matchesDesc = poi.description?.toLowerCase().includes(q)
      if (!matchesTitle && !matchesDesc) return false
    }
    return true
  })
})

// Смена активного этажа
function handleSelectFloor(floor: Floor) {
  activeFloor.value = floor
  // Если выбранный POI не на новом этаже — скрываем карточку POI
  if (selectedPoi.value && selectedPoi.value.floor_id !== floor.id) {
    selectedPoi.value = null
  }
}

// Выбор POI из карты или поиска
function handleSelectPoi(poi: POI) {
  // Если включен режим выбора точки старта на карте — задаем эту POI как старт
  if (isPickingStartOnMap.value) {
    handleSetAsOrigin(poi)
    isPickingStartOnMap.value = false
    return
  }

  selectedPoi.value = poi

  // Если точка на другом этаже — автоматически переключаем этаж
  if (activeFloor.value && poi.floor_id !== activeFloor.value.id) {
    const targetFloor = space.value?.floors.find((f) => f.id === poi.floor_id)
    if (targetFloor) {
      activeFloor.value = targetFloor
    }
  }
}

// Закрытие карточки POI
function handleCloseBottomSheet() {
  selectedPoi.value = null
}

// Задать POI как точку отправления («Начать отсюда»)
function handleSetAsOrigin(poi: POI) {
  routeOrigin.value = {
    x: poi.x,
    y: poi.y,
    floor_id: poi.floor_id,
    title: poi.title,
    poiId: poi.id,
  }
  selectedPoi.value = null

  // Если целевая точка уже выбрана — сразу строим маршрут
  if (routeTarget.value) {
    calculateRoute()
  }
}

// Переключение режима выбора старта на карте
function togglePickOriginOnMap() {
  isPickingStartOnMap.value = !isPickingStartOnMap.value
}

// Клик по карте в произвольное место
function handleMapClick(coords: { x: number; y: number; floor_id: string }) {
  if (isPickingStartOnMap.value) {
    routeOrigin.value = {
      x: coords.x,
      y: coords.y,
      floor_id: coords.floor_id,
      title: `Точка (${coords.x}, ${coords.y})`,
    }
    isPickingStartOnMap.value = false
    if (routeTarget.value) {
      calculateRoute()
    }
  }
}

// Перетаскивание маркера старта "A" по карте с автопересчетом
function handleUpdateOrigin(coords: { x: number; y: number; floor_id: string }) {
  routeOrigin.value = {
    x: coords.x,
    y: coords.y,
    floor_id: coords.floor_id,
    title: 'Выбранная точка',
    poiId: undefined,
  }
  if (routeTarget.value) {
    calculateRoute()
  }
}

// Расчет маршрута между routeOrigin и routeTarget
async function calculateRoute() {
  if (!space.value || !routeTarget.value || !routeOrigin.value) return

  const origin: RoutePoint = {
    x: routeOrigin.value.x,
    y: routeOrigin.value.y,
    floor_id: routeOrigin.value.floor_id,
  }

  const destination: RoutePoint = {
    x: routeTarget.value.x,
    y: routeTarget.value.y,
    floor_id: routeTarget.value.floor_id,
  }

  routeErrorMessage.value = null

  try {
    const routeData = await getRoute({
      origin,
      destination,
      spaceId: space.value.id,
      to_poi_id: routeTarget.value.id,
    })
    activeRoute.value = routeData
    isRouting.value = true
    selectedPoi.value = null
  } catch (err: any) {
    console.error('Ошибка расчета маршрута:', err)
    activeRoute.value = null
    isRouting.value = false
    const detail = err.response?.data?.detail || err.message || ''
    routeErrorMessage.value = detail.includes('No path') || detail.includes('не найден')
      ? 'Маршрут не найден: между точками нет прохода через граф или путь прегражден стенами.'
      : 'Не удалось построить маршрут между выбранными точками.'
  }
}

// Построение маршрута до выбранной точки («Маршрут сюда»)
async function handleBuildRoute(targetPoi: POI) {
  if (!space.value || !activeFloor.value) return

  routeTarget.value = targetPoi

  // Если точка отправления еще не задана — ищем вход на текущем этаже или центр этажа
  if (!routeOrigin.value) {
    const entrancePoi = space.value.pois.find(
      (p) => p.category === 'entrance' && p.floor_id === activeFloor.value?.id
    ) || space.value.pois.find((p) => p.category === 'entrance')

    if (entrancePoi) {
      routeOrigin.value = {
        x: entrancePoi.x,
        y: entrancePoi.y,
        floor_id: entrancePoi.floor_id,
        title: entrancePoi.title || 'Главный вход',
        poiId: entrancePoi.id,
      }
    } else {
      routeOrigin.value = {
        x: Math.round((activeFloor.value.width || 1000) / 2),
        y: Math.round((activeFloor.value.height || 800) / 2),
        floor_id: activeFloor.value.id,
        title: 'Текущая позиция',
      }
    }
  }

  await calculateRoute()
}

// Сброс активного маршрута
function handleResetRoute() {
  isRouting.value = false
  activeRoute.value = null
  routeOrigin.value = null
  routeTarget.value = null
  isPickingStartOnMap.value = false
  routeErrorMessage.value = null
}

// Открытие виртуального тура 360°
function handleOpenPanorama(poi: POI) {
  panoramaPoi.value = poi
  isPanoramaOpen.value = true
}

function handleOpenVirtualTour() {
  // Открываем тур для точки назначения маршрута или первого попавшегося стенда
  const targetPoi = selectedPoi.value || space.value?.pois.find((p) => p.panorama_id)
  if (targetPoi) {
    handleOpenPanorama(targetPoi)
  }
}

function handleClosePanorama() {
  isPanoramaOpen.value = false
  panoramaPoi.value = null
}

onMounted(() => {
  loadSpaceData()
})

watch(
  () => currentSlug.value,
  () => {
    loadSpaceData()
  }
)
</script>

<template>
  <main class="relative w-full h-[100dvh] min-h-[100dvh] bg-slate-950 overflow-hidden flex flex-col select-none">
    <!-- Индикатор загрузки -->
    <div
      v-if="isLoading"
      class="absolute inset-0 z-50 bg-slate-950 flex flex-col items-center justify-center gap-3 text-slate-100"
    >
      <Loader2 class="w-8 h-8 text-blue-500 animate-spin" />
      <span class="text-sm font-medium text-slate-300">Загрузка площадки и плана...</span>
    </div>

    <!-- Индикатор ошибки -->
    <div
      v-else-if="errorMessage"
      class="absolute inset-0 z-50 bg-slate-950 flex flex-col items-center justify-center p-6 text-center gap-4 text-slate-100"
    >
      <AlertCircle class="w-12 h-12 text-red-500" />
      <div class="max-w-md">
        <h2 class="text-lg font-bold text-white">{{ errorMessage }}</h2>
        <p class="text-sm text-slate-400 mt-1">Проверьте подключение к серверу или обратитесь к организаторам.</p>
      </div>
      <button
        type="button"
        class="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-all"
        @click="loadSpaceData"
      >
        Попробовать снова
      </button>
    </div>

    <!-- Основной рабочий экран -->
    <template v-else-if="space && activeFloor">
      <!-- Баннер предпросмотра черновика -->
      <div
        v-if="space.is_published === false"
        class="absolute top-0 left-0 right-0 z-30 bg-amber-500/90 backdrop-blur-md text-amber-950 px-4 py-1.5 text-center text-xs font-semibold shadow-md flex items-center justify-center gap-2"
        style="padding-top: max(0.375rem, env(safe-area-inset-top, 0px));"
      >
        <span>⚠️ Режим предпросмотра: пространство не опубликовано (черновик)</span>
      </div>

      <!-- Карта Leaflet (фоновый интерактивный слой) -->
      <div class="absolute inset-0 z-0">
        <ViewerMap
          :floor="activeFloor"
          :pois="filteredPois"
          :selected-poi="selectedPoi"
          :route="activeRoute"
          :is-routing="isRouting"
          :origin-point="routeOrigin"
          :is-picking-origin="isPickingStartOnMap"
          :blueprint-opacity="blueprintOpacity"
          @select-poi="handleSelectPoi"
          @map-click="handleMapClick"
          @update-origin="handleUpdateOrigin"
        />
      </div>

      <!-- Всплывающее уведомление об ошибке маршрута -->
      <transition
        enter-active-class="transition duration-300 ease-out transform"
        enter-from-class="-translate-y-4 opacity-0"
        enter-to-class="translate-y-0 opacity-100"
        leave-active-class="transition duration-200 ease-in transform"
        leave-from-class="translate-y-0 opacity-100"
        leave-to-class="-translate-y-4 opacity-0"
      >
        <div
          v-if="routeErrorMessage"
          class="absolute top-20 left-1/2 -translate-x-1/2 z-40 max-w-md w-[92%] sm:w-auto bg-rose-950/95 border border-rose-500/50 text-rose-200 px-4 py-3 rounded-2xl shadow-2xl backdrop-blur-md flex items-center justify-between gap-3 pointer-events-auto"
        >
          <div class="flex items-center gap-2.5">
            <AlertCircle class="w-5 h-5 text-rose-400 shrink-0" />
            <span class="text-xs sm:text-sm font-medium">{{ routeErrorMessage }}</span>
          </div>
          <button
            type="button"
            @click="routeErrorMessage = null"
            class="text-rose-400 hover:text-white p-1 rounded-lg transition-colors cursor-pointer"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
      </transition>

      <!-- Плавающий контрол прозрачности подложки (для пользователей) -->
      <div class="absolute left-3 bottom-24 sm:bottom-8 z-20 pointer-events-auto">
        <div class="relative">
          <button
            type="button"
            @click="showOpacityMenu = !showOpacityMenu"
            class="w-10 h-10 rounded-xl bg-slate-900/90 border border-slate-700/70 text-slate-300 hover:text-white hover:bg-slate-800 shadow-xl backdrop-blur-md flex items-center justify-center transition-all cursor-pointer"
            title="Прозрачность подложки чертежа"
          >
            <Sliders class="w-5 h-5" />
          </button>

          <transition
            enter-active-class="transition duration-150 ease-out transform"
            enter-from-class="scale-95 opacity-0"
            enter-to-class="scale-100 opacity-100"
            leave-active-class="transition duration-100 ease-in transform"
            leave-from-class="scale-100 opacity-100"
            leave-to-class="scale-95 opacity-0"
          >
            <div
              v-if="showOpacityMenu"
              class="absolute bottom-12 left-0 w-60 p-3 rounded-2xl bg-slate-900/95 border border-slate-700/80 shadow-2xl backdrop-blur-md flex flex-col gap-2.5 text-xs text-slate-200 z-50"
            >
              <div class="flex items-center justify-between font-medium">
                <span class="flex items-center gap-1.5 text-slate-300">
                  <Layers class="w-3.5 h-3.5 text-blue-400" /> Подложка
                </span>
                <span class="font-mono text-blue-400 font-semibold">{{ Math.round(blueprintOpacity * 100) }}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                v-model.number="blueprintOpacity"
                class="w-full accent-blue-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg appearance-none"
              />
              <div class="grid grid-cols-3 gap-1 pt-1">
                <button
                  type="button"
                  @click="blueprintOpacity = 0"
                  class="px-1.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-center font-medium transition-colors"
                  :class="{ 'ring-1 ring-blue-500 text-blue-400 font-bold': blueprintOpacity === 0 }"
                >
                  Только схема
                </button>
                <button
                  type="button"
                  @click="blueprintOpacity = 0.5"
                  class="px-1.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-center font-medium transition-colors"
                  :class="{ 'ring-1 ring-blue-500 text-blue-400 font-bold': blueprintOpacity === 0.5 }"
                >
                  50%
                </button>
                <button
                  type="button"
                  @click="blueprintOpacity = 0.85"
                  class="px-1.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[10px] text-center font-medium transition-colors"
                  :class="{ 'ring-1 ring-blue-500 text-blue-400 font-bold': blueprintOpacity === 0.85 }"
                >
                  85%
                </button>
              </div>
            </div>
          </transition>
        </div>
      </div>

      <!-- ВЕРХНИЙ ОВЕРЛЕЙ: Поиск и чипсы категорий -->
      <header
        class="absolute left-0 right-0 z-20 p-2.5 sm:p-4 max-w-2xl mx-auto pointer-events-none"
        :class="space.is_published === false ? 'top-8' : 'top-0'"
        style="padding-top: max(0.625rem, env(safe-area-inset-top, 0px));"
      >
        <ViewerSearch
          v-model="searchQuery"
          v-model:selected-category="selectedCategory"
          :pois="space.pois"
          @select-poi="handleSelectPoi"
        />
      </header>

      <!-- ПРАВЫЙ ОВЕРЛЕЙ: Плавающий переключатель этажей -->
      <div
        class="absolute right-2.5 sm:right-5 z-20 pointer-events-none"
        :class="space.is_published === false ? 'top-36' : 'top-24 sm:top-28'"
      >
        <FloorSelector
          :floors="space.floors"
          :active-floor-id="activeFloor.id"
          @select-floor="handleSelectFloor"
        />
      </div>

      <!-- НИЖНИЙ ОВЕРЛЕЙ: Bottom Sheet карточки POI или Плашка маршрута -->
      <footer
        class="absolute bottom-0 left-0 right-0 z-20 p-2.5 sm:p-4 pointer-events-none flex flex-col items-center"
        style="padding-bottom: max(0.625rem, env(safe-area-inset-bottom, 0px));"
      >
        <!-- Плашка активного маршрута -->
        <RouteBar
          v-if="isRouting && activeRoute"
          :route="activeRoute"
          :target-poi-title="routeTarget?.title || selectedPoi?.title"
          :origin-title="routeOrigin?.title"
          :is-picking-origin="isPickingStartOnMap"
          @reset="handleResetRoute"
          @open-virtual-tour="handleOpenVirtualTour"
          @pick-origin-on-map="togglePickOriginOnMap"
        />

        <!-- Bottom Sheet выбранного POI -->
        <PoiBottomSheet
          v-else-if="selectedPoi"
          :poi="selectedPoi"
          :floor-title="activeFloor.title"
          @close="handleCloseBottomSheet"
          @build-route="handleBuildRoute"
          @set-as-origin="handleSetAsOrigin"
          @open-panorama="handleOpenPanorama"
        />
      </footer>

      <!-- Модальное окно 360° виртуального тура -->
      <PanoramaModal
        v-if="isPanoramaOpen && panoramaPoi"
        :poi="panoramaPoi"
        @close="handleClosePanorama"
      />
    </template>

    <!-- Состояние: в пространстве еще нет этажей с планами -->
    <div
      v-else-if="space"
      class="absolute inset-0 z-50 bg-slate-950 flex flex-col items-center justify-center p-6 text-center gap-4 text-slate-100"
    >
      <div class="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-400 mb-2">
        <Layers class="w-8 h-8 text-blue-500" />
      </div>
      <div class="max-w-md">
        <h2 class="text-xl font-bold text-white">{{ space.title }}</h2>
        <p class="text-sm text-slate-400 mt-2">
          В этом пространстве пока нет планов этажей. Загрузите чертеж или схему в студии управления.
        </p>
      </div>
      <router-link
        to="/admin/spaces"
        class="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-medium text-sm transition-all"
      >
        Перейти в управление пространствами
      </router-link>
    </div>
  </main>
</template>
