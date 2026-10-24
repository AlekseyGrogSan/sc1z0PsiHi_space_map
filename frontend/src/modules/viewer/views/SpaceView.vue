<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Loader2, AlertCircle, Layers } from 'lucide-vue-next'
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
    ...routeOrigin.value,
    x: coords.x,
    y: coords.y,
    floor_id: coords.floor_id,
    title: routeOrigin.value?.title || `Точка (${coords.x}, ${coords.y})`,
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
  } catch (err) {
    console.error('Ошибка расчета маршрута:', err)
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
  <main class="relative w-full h-full min-h-screen bg-slate-950 overflow-hidden flex flex-col">
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
          @select-poi="handleSelectPoi"
          @map-click="handleMapClick"
          @update-origin="handleUpdateOrigin"
        />
      </div>

      <!-- ВЕРХНИЙ ОВЕРЛЕЙ: Поиск и чипсы категорий -->
      <header
        class="absolute left-0 right-0 z-20 p-3 sm:p-4 max-w-2xl mx-auto pointer-events-none"
        :class="space.is_published === false ? 'top-8' : 'top-0'"
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
        class="absolute right-3 sm:right-5 z-20 pointer-events-none"
        :class="space.is_published === false ? 'top-36' : 'top-28'"
      >
        <FloorSelector
          :floors="space.floors"
          :active-floor-id="activeFloor.id"
          @select-floor="handleSelectFloor"
        />
      </div>

      <!-- НИЖНИЙ ОВЕРЛЕЙ: Bottom Sheet карточки POI или Плашка маршрута -->
      <footer class="absolute bottom-0 left-0 right-0 z-20 p-3 sm:p-4 pointer-events-none flex flex-col items-center">
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
