<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import type { Floor, POI, RouteResponse, PoiCategory } from '../types'

interface Props {
  floor: Floor
  pois: POI[]
  selectedPoi: POI | null
  route: RouteResponse | null
  isRouting: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'selectPoi', poi: POI): void
}>()

const mapContainer = ref<HTMLDivElement | null>(null)
let map: L.Map | null = null
let currentOverlay: L.ImageOverlay | null = null
let markerGroup: L.LayerGroup | null = null
let routePolyline: L.Polyline | null = null
let routeEndpointsGroup: L.LayerGroup | null = null

// Категории и их цветовое оформление
const categoryColors: Record<PoiCategory, { bg: string; border: string; glow: string }> = {
  stand: { bg: '#2563eb', border: '#60a5fa', glow: 'rgba(37,99,235,0.6)' },
  food: { bg: '#d97706', border: '#fbbf24', glow: 'rgba(217,119,6,0.6)' },
  wc: { bg: '#0891b2', border: '#22d3ee', glow: 'rgba(8,145,178,0.6)' },
  stage: { bg: '#7c3aed', border: '#c084fc', glow: 'rgba(124,58,237,0.6)' },
  entrance: { bg: '#059669', border: '#34d399', glow: 'rgba(5,150,105,0.6)' },
  wifi: { bg: '#0284c7', border: '#38bdf8', glow: 'rgba(2,132,199,0.6)' },
  info: { bg: '#475569', border: '#94a3b8', glow: 'rgba(71,85,105,0.6)' },
}

// SVG иконки для L.divIcon бейджей
function getCategoryIconSvg(category: PoiCategory, size: number = 18): string {
  switch (category) {
    case 'stand':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M8 10h.01"/><path d="M16 10h.01"/><path d="M8 14h.01"/><path d="M16 14h.01"/></svg>`
    case 'food':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2v6a3 3 0 0 1-3 3 3 3 0 0 1-3-3V2"/><path d="M15 2v14"/><path d="M15 16a3 3 0 0 0-3 3v3"/><path d="M6 2v20"/><path d="M3 2v4a3 3 0 0 0 3 3h0a3 3 0 0 0 3-3V2"/></svg>`
    case 'wc':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6 6.5 3.5a1.5 1.5 0 0 0-1 0L3 6"/><path d="M2 12h20"/><path d="M7 19v2"/><path d="M17 19v2"/><path d="M4 12v4a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-4"/></svg>`
    case 'stage':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`
    case 'entrance':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 4h3a2 2 0 0 1 2 2v14"/><path d="M2 20h20"/><path d="M13 20V4a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v16"/><circle cx="9" cy="12" r="1"/></svg>`
    case 'wifi':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.86a10 10 0 0 1 14 0"/><path d="M8.5 16.43a5 5 0 0 1 7 0"/></svg>`
    default:
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`
  }
}

// Преобразование координат (x, y) плана этажа в LatLng Leaflet [lat, lng]
function toLatLng(x: number, y: number, height: number): [number, number] {
  return [height - y, x]
}

// Создание HTML для маркера POI
function createMarkerHtml(poi: POI, isSelected: boolean): string {
  const cfg = categoryColors[poi.category] || categoryColors.stand
  const size = isSelected ? 44 : 36
  const iconSize = isSelected ? 22 : 18
  const ringStyle = isSelected
    ? `box-shadow: 0 0 0 4px #ffffff, 0 0 24px ${cfg.glow}; transform: scale(1.15);`
    : `box-shadow: 0 4px 12px rgba(0, 0, 0, 0.6);`

  return `
    <div style="
      width: ${size}px;
      height: ${size}px;
      background-color: ${cfg.bg};
      border: 2.5px solid ${cfg.border};
      border-radius: 9999px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      ${ringStyle}
    ">
      ${getCategoryIconSvg(poi.category, iconSize)}
    </div>
  `
}

function handleResize() {
  if (map) {
    map.invalidateSize()
  }
}

function initMap() {
  if (!mapContainer.value) return

  // Инициализация Leaflet с L.CRS.Simple
  map = L.map(mapContainer.value, {
    crs: L.CRS.Simple,
    minZoom: -1.5,
    maxZoom: 2,
    zoomSnap: 0.25,
    attributionControl: false,
    zoomControl: false,
  })

  markerGroup = L.layerGroup().addTo(map)
  routeEndpointsGroup = L.layerGroup().addTo(map)

  renderFloorPlan()
  renderMarkers()
  renderRoute()

  window.addEventListener('resize', handleResize)

  setTimeout(() => {
    if (map) {
      map.invalidateSize()
      const bounds: L.LatLngBoundsExpression = [
        [0, 0],
        [props.floor.height, props.floor.width],
      ]
      map.fitBounds(bounds, { animate: false, padding: [20, 20] })
    }
  }, 150)
}

function renderFloorPlan() {
  if (!map) return

  if (currentOverlay) {
    map.removeLayer(currentOverlay)
    currentOverlay = null
  }

  const bounds: L.LatLngBoundsExpression = [
    [0, 0],
    [props.floor.height, props.floor.width],
  ]

  currentOverlay = L.imageOverlay(props.floor.plan_image_url, bounds).addTo(map)
  map.fitBounds(bounds, { animate: true, padding: [20, 20] })

  setTimeout(() => {
    if (map) {
      map.invalidateSize()
    }
  }, 100)
}

function renderMarkers() {
  if (!map || !markerGroup) return
  markerGroup.clearLayers()

  // Фильтрация точек по текущему этажу
  const currentFloorPois = props.pois.filter((p) => p.floor_id === props.floor.id)

  currentFloorPois.forEach((poi) => {
    const isSelected = props.selectedPoi?.id === poi.id
    const latlng = toLatLng(poi.x, poi.y, props.floor.height)
    const iconSize = isSelected ? 44 : 36

    const icon = L.divIcon({
      className: 'poi-custom-div-icon',
      html: createMarkerHtml(poi, isSelected),
      iconSize: [iconSize, iconSize],
      iconAnchor: [iconSize / 2, iconSize / 2],
    })

    const marker = L.marker(latlng, { icon, zIndexOffset: isSelected ? 1000 : 100 })
    marker.on('click', () => {
      emit('selectPoi', poi)
      map?.panTo(latlng, { animate: true, duration: 0.4 })
    })

    markerGroup?.addLayer(marker)
  })
}

function renderRoute() {
  if (!map) return

  if (routePolyline) {
    map.removeLayer(routePolyline)
    routePolyline = null
  }

  if (routeEndpointsGroup) {
    routeEndpointsGroup.clearLayers()
  }

  if (!props.isRouting || !props.route || !props.route.points?.length) return

  // Получаем точки маршрута для текущего этажа
  const floorPoints = props.route.points.filter((p) => p.floor_id === props.floor.id)
  if (floorPoints.length < 2) return

  const latlngs: [number, number][] = floorPoints.map((p) =>
    toLatLng(p.x, p.y, props.floor.height)
  )

  // Отрисовка цветной полилинии маршрута (#3b82f6, dashArray: '8, 8')
  routePolyline = L.polyline(latlngs, {
    color: '#3b82f6',
    weight: 6,
    opacity: 0.95,
    dashArray: '8, 8',
    lineCap: 'round',
    lineJoin: 'round',
  }).addTo(map)

  // Начальная и конечная точки маршрута
  const startLatlng = latlngs[0]
  const endLatlng = latlngs[latlngs.length - 1]

  const startIcon = L.divIcon({
    className: 'route-start-icon',
    html: `
      <div style="width: 22px; height: 22px; background-color: #10b981; border: 3px solid #ffffff; border-radius: 9999px; box-shadow: 0 0 10px rgba(16,185,129,0.8);"></div>
    `,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  })

  const endIcon = L.divIcon({
    className: 'route-end-icon',
    html: `
      <div style="width: 26px; height: 26px; background-color: #e30613; border: 3px solid #ffffff; border-radius: 9999px; box-shadow: 0 0 12px rgba(227,6,19,0.9); animation: pulse 1.5s infinite;"></div>
    `,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })

  L.marker(startLatlng, { icon: startIcon, zIndexOffset: 2000 }).addTo(routeEndpointsGroup!)
  L.marker(endLatlng, { icon: endIcon, zIndexOffset: 2000 }).addTo(routeEndpointsGroup!)
}

// Следим за сменой этажа -> перерисовываем оверлей, авто fitBounds и маркеры
watch(
  () => props.floor.id,
  () => {
    renderFloorPlan()
    renderMarkers()
    renderRoute()
  }
)

// Следим за точками интереса и выбором
watch([() => props.pois, () => props.selectedPoi], () => {
  renderMarkers()
  if (props.selectedPoi && props.selectedPoi.floor_id === props.floor.id && map) {
    const latlng = toLatLng(props.selectedPoi.x, props.selectedPoi.y, props.floor.height)
    map.panTo(latlng, { animate: true, duration: 0.4 })
  }
})

// Следим за маршрутом
watch([() => props.route, () => props.isRouting], () => {
  renderRoute()
})

onMounted(() => {
  initMap()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (map) {
    map.remove()
    map = null
  }
})
</script>

<template>
  <div class="relative w-full h-full bg-slate-950 overflow-hidden">
    <!-- Контейнер Leaflet карты -->
    <div ref="mapContainer" class="w-full h-full select-none outline-none"></div>
  </div>
</template>

<style>
/* Стили для кастомных Leaflet divIcon */
.poi-custom-div-icon,
.route-start-icon,
.route-end-icon {
  background: transparent !important;
  border: none !important;
}

.leaflet-container {
  background-color: #020617 !important;
  font-family: inherit;
}
</style>
