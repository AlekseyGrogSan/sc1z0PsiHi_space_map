<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { resolveMediaUrl } from '../../../api/client'
import type { Floor, POI, RouteResponse, PoiCategory, RoutePoint } from '../types'

interface Props {
  floor: Floor
  pois: POI[]
  selectedPoi: POI | null
  route: RouteResponse | null
  isRouting: boolean
  originPoint?: RoutePoint | null
  isPickingOrigin?: boolean
  blueprintOpacity?: number
}

const props = defineProps<Props>()

async function getRotatedPlanUrl(imageUrl: string, degrees: number): Promise<string> {
  const normDeg = ((degrees % 360) + 360) % 360
  if (normDeg === 0) return imageUrl

  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d')
        if (!ctx) return resolve(imageUrl)
        if (normDeg === 90 || normDeg === 270) {
          canvas.width = img.height
          canvas.height = img.width
        } else {
          canvas.width = img.width
          canvas.height = img.height
        }
        ctx.translate(canvas.width / 2, canvas.height / 2)
        ctx.rotate((normDeg * Math.PI) / 180)
        ctx.drawImage(img, -img.width / 2, -img.height / 2)
        resolve(canvas.toDataURL('image/png'))
      } catch (e) {
        resolve(imageUrl)
      }
    }
    img.onerror = () => resolve(imageUrl)
    img.src = imageUrl
  })
}

const emit = defineEmits<{
  (e: 'selectPoi', poi: POI): void
  (e: 'mapClick', coords: { x: number; y: number; floor_id: string }): void
  (e: 'updateOrigin', coords: { x: number; y: number; floor_id: string }): void
}>()

const mapContainer = ref<HTMLDivElement | null>(null)
let map: L.Map | null = null
let currentOverlay: L.ImageOverlay | null = null
let markerGroup: L.LayerGroup | null = null
let routePolyline: L.Polyline | null = null
let routeEndpointsGroup: L.LayerGroup | null = null
let layoutGroup: L.LayerGroup | null = null

// Категории и их цветовое оформление
const categoryColors: Record<PoiCategory, { bg: string; border: string; glow: string }> = {
  stand: { bg: '#2563eb', border: '#60a5fa', glow: 'rgba(37,99,235,0.6)' },
  retail: { bg: '#0284c7', border: '#38bdf8', glow: 'rgba(2,132,199,0.6)' },
  entertainment: { bg: '#9333ea', border: '#c084fc', glow: 'rgba(147,51,234,0.6)' },
  food: { bg: '#d97706', border: '#fbbf24', glow: 'rgba(217,119,6,0.6)' },
  bench: { bg: '#b45309', border: '#fcd34d', glow: 'rgba(180,83,9,0.6)' },
  trash: { bg: '#475569', border: '#94a3b8', glow: 'rgba(71,85,105,0.6)' },
  wc: { bg: '#0891b2', border: '#22d3ee', glow: 'rgba(8,145,178,0.6)' },
  stage: { bg: '#7c3aed', border: '#c084fc', glow: 'rgba(124,58,237,0.6)' },
  entrance: { bg: '#059669', border: '#34d399', glow: 'rgba(5,150,105,0.6)' },
  exit: { bg: '#dc2626', border: '#f87171', glow: 'rgba(220,38,38,0.6)' },
  wifi: { bg: '#0284c7', border: '#38bdf8', glow: 'rgba(2,132,199,0.6)' },
  info: { bg: '#475569', border: '#94a3b8', glow: 'rgba(71,85,105,0.6)' },
  custom: { bg: '#0d9488', border: '#2dd4bf', glow: 'rgba(13,148,136,0.6)' },
}

// SVG иконки для L.divIcon бейджей
function getCategoryIconSvg(category: PoiCategory, size: number = 18): string {
  switch (category) {
    case 'stand':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2" ry="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01"/><path d="M16 6h.01"/><path d="M8 10h.01"/><path d="M16 10h.01"/><path d="M8 14h.01"/><path d="M16 14h.01"/></svg>`
    case 'retail':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>`
    case 'entertainment':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" x2="10" y1="12" y2="12"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="15" x2="15.01" y1="13" y2="13"/><line x1="18" x2="18.01" y1="11" y2="11"/><rect width="20" height="12" x="2" y="6" rx="6"/></svg>`
    case 'food':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2v6a3 3 0 0 1-3 3 3 3 0 0 1-3-3V2"/><path d="M15 2v14"/><path d="M15 16a3 3 0 0 0-3 3v3"/><path d="M6 2v20"/><path d="M3 2v4a3 3 0 0 0 3 3h0a3 3 0 0 0 3-3V2"/></svg>`
    case 'bench':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v3"/><path d="M2 11v5a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v2H6v-2a2 2 0 0 0-4 0Z"/><path d="M4 18v2"/><path d="M20 18v2"/></svg>`
    case 'trash':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>`
    case 'wc':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6 6.5 3.5a1.5 1.5 0 0 0-1 0L3 6"/><path d="M2 12h20"/><path d="M7 19v2"/><path d="M17 19v2"/><path d="M4 12v4a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3v-4"/></svg>`
    case 'stage':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`
    case 'entrance':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 4h3a2 2 0 0 1 2 2v14"/><path d="M2 20h20"/><path d="M13 20V4a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v16"/><circle cx="9" cy="12" r="1"/></svg>`
    case 'exit':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>`
    case 'wifi':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h.01"/><path d="M2 8.82a15 15 0 0 1 20 0"/><path d="M5 12.86a10 10 0 0 1 14 0"/><path d="M8.5 16.43a5 5 0 0 1 7 0"/></svg>`
    case 'custom':
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`
    default:
      return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`
  }
}

// Преобразование координат (x, y) плана этажа в LatLng Leaflet [lat, lng]
function toLatLng(x: number, y: number, _height?: number): [number, number] {
  return [y, x]
}

// Создание HTML для маркера POI с 2-строчной подписью
function createMarkerHtml(poi: POI, isSelected: boolean): string {
  const cfg = categoryColors[poi.category] || categoryColors.stand
  const size = isSelected ? 40 : 32
  const iconSize = isSelected ? 20 : 16
  const ringStyle = isSelected
    ? `box-shadow: 0 0 0 3px #ffffff, 0 0 20px ${cfg.glow}; transform: scale(1.1);`
    : `box-shadow: 0 4px 10px rgba(0, 0, 0, 0.5);`

  return `
    <div class="poi-marker-wrap flex flex-col items-center pointer-events-auto">
      <div style="
        position: relative;
        width: ${size}px;
        height: ${size}px;
        background-color: ${cfg.bg};
        border: 2px solid ${cfg.border};
        border-radius: 9999px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        ${ringStyle}
      ">
        ${getCategoryIconSvg(poi.category, iconSize)}
        ${poi.panorama_id ? `
          <div style="
            position: absolute;
            top: -5px;
            right: -7px;
            background: #a855f7;
            color: #ffffff;
            font-size: 8.5px;
            font-weight: 700;
            padding: 1px 4px;
            border-radius: 9999px;
            border: 1px solid rgba(255,255,255,0.8);
            box-shadow: 0 2px 4px rgba(0,0,0,0.5);
            line-height: 1.1;
          ">360°</div>
        ` : ''}
      </div>
      <div class="poi-label mt-1 px-1.5 py-0.5 rounded bg-slate-900/80 backdrop-blur-sm border border-slate-700/60 text-center text-slate-200 pointer-events-none select-none transition-all">
        <span class="poi-label-text block font-medium leading-tight">${poi.title}</span>
      </div>
    </div>
  `
}

function getCorridorPolygon(c: any): [number, number][] {
  const x1 = Number(c.x1)
  const y1 = Number(c.y1)
  const x2 = Number(c.x2)
  const y2 = Number(c.y2)
  const r = (Number(c.width) || 24) / 2.0
  const dx = x2 - x1
  const dy = y2 - y1
  const len = Math.hypot(dx, dy)

  const pts: [number, number][] = []
  if (len < 0.1) {
    const num = 16
    for (let i = 0; i < num; i++) {
      const a = (i * 2 * Math.PI) / num
      pts.push([y1 + r * Math.sin(a), x1 + r * Math.cos(a)])
    }
    return pts
  }

  const baseAngle = Math.atan2(dy, dx)
  const numArc = 8

  for (let i = 0; i <= numArc; i++) {
    const a = baseAngle - Math.PI / 2 + (i * Math.PI) / numArc
    pts.push([y2 + r * Math.sin(a), x2 + r * Math.cos(a)])
  }

  for (let i = 0; i <= numArc; i++) {
    const a = baseAngle + Math.PI / 2 + (i * Math.PI) / numArc
    pts.push([y1 + r * Math.sin(a), x1 + r * Math.cos(a)])
  }

  return pts
}

function getFloorNavigableBounds(floor: any): { minX: number; minY: number; maxX: number; maxY: number } {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity

  const layout = floor?.layout_data
  if (layout) {
    // 1. Rooms
    if (Array.isArray(layout.rooms)) {
      for (const r of layout.rooms) {
        if (Array.isArray(r.points) && r.points.length > 0) {
          for (const pt of r.points) {
            const px = Number(pt[0]), py = Number(pt[1])
            if (!isNaN(px) && !isNaN(py)) {
              minX = Math.min(minX, px)
              maxX = Math.max(maxX, px)
              minY = Math.min(minY, py)
              maxY = Math.max(maxY, py)
            }
          }
        } else if (r.x !== undefined && r.y !== undefined) {
          const rx = Number(r.x), ry = Number(r.y)
          const rw = Number(r.width || 0), rh = Number(r.height || 0)
          minX = Math.min(minX, rx)
          maxX = Math.max(maxX, rx + rw)
          minY = Math.min(minY, ry)
          maxY = Math.max(maxY, ry + rh)
        }
      }
    }

    // 2. Walls
    if (Array.isArray(layout.walls)) {
      for (const w of layout.walls) {
        minX = Math.min(minX, Number(w.x1), Number(w.x2))
        maxX = Math.max(maxX, Number(w.x1), Number(w.x2))
        minY = Math.min(minY, Number(w.y1), Number(w.y2))
        maxY = Math.max(maxY, Number(w.y1), Number(w.y2))
      }
    }

    // 3. Corridors
    if (Array.isArray(layout.corridors)) {
      for (const c of layout.corridors) {
        const halfW = (Number(c.width) || 35) / 2
        minX = Math.min(minX, Number(c.x1) - halfW, Number(c.x2) - halfW)
        maxX = Math.max(maxX, Number(c.x1) + halfW, Number(c.x2) + halfW)
        minY = Math.min(minY, Number(c.y1) - halfW, Number(c.y2) - halfW)
        maxY = Math.max(maxY, Number(c.y1) + halfW, Number(c.y2) + halfW)
      }
    }

    // 4. Obstacles
    if (Array.isArray(layout.obstacles)) {
      for (const o of layout.obstacles) {
        if (o.type === 'circle') {
          const r = Number(o.radius || 30)
          minX = Math.min(minX, Number(o.x) - r)
          maxX = Math.max(maxX, Number(o.x) + r)
          minY = Math.min(minY, Number(o.y) - r)
          maxY = Math.max(maxY, Number(o.y) + r)
        } else {
          minX = Math.min(minX, Number(o.x))
          maxX = Math.max(maxX, Number(o.x) + Number(o.width || 0))
          minY = Math.min(minY, Number(o.y))
          maxY = Math.max(maxY, Number(o.y) + Number(o.height || 0))
        }
      }
    }
  }

  const fw = floor?.width || floor?.width_px || 1600
  const fh = floor?.height || floor?.height_px || 900

  if (minX === Infinity || maxX === -Infinity) {
    return { minX: 0, minY: 0, maxX: fw, maxY: fh }
  }

  return {
    minX: Math.max(0, Math.round(minX)),
    minY: Math.max(0, Math.round(minY)),
    maxX: Math.min(fw, Math.round(maxX)),
    maxY: Math.min(fh, Math.round(maxY)),
  }
}

function snapPointToNavigable(x: number, y: number): { x: number; y: number } {
  const bounds = getFloorNavigableBounds(props.floor)
  const margin = 12
  let curX = Math.max(bounds.minX + margin, Math.min(bounds.maxX - margin, x))
  let curY = Math.max(bounds.minY + margin, Math.min(bounds.maxY - margin, y))

  if (!props.floor.layout_data) return { x: curX, y: curY }
  const { obstacles, walls } = props.floor.layout_data

  // 1. Проверка круглых препятствий
  if (Array.isArray(obstacles)) {
    for (const o of obstacles) {
      if (o.type === 'circle') {
        const ox = Number(o.x)
        const oy = Number(o.y)
        const rad = Number(o.radius || 30)
        const dist = Math.hypot(curX - ox, curY - oy)
        if (dist < rad + 4) {
          const angle = dist > 0.1 ? Math.atan2(curY - oy, curX - ox) : 0
          curX = Math.round(ox + (rad + 10) * Math.cos(angle))
          curY = Math.round(oy + (rad + 10) * Math.sin(angle))
        }
      } else if (o.type === 'rect') {
        const rx = Number(o.x)
        const ry = Number(o.y)
        const rw = Number(o.width)
        const rh = Number(o.height)
        if (curX >= rx - 4 && curX <= rx + rw + 4 && curY >= ry - 4 && curY <= ry + rh + 4) {
          const dLeft = curX - rx
          const dRight = rx + rw - curX
          const dBottom = curY - ry
          const dTop = ry + rh - curY
          const minD = Math.min(dLeft, dRight, dBottom, dTop)
          if (minD === dLeft) curX = rx - 10
          else if (minD === dRight) curX = rx + rw + 10
          else if (minD === dBottom) curY = ry - 10
          else curY = ry + rh + 10
        }
      }
    }
  }

  // 2. Проверка стен
  if (Array.isArray(walls)) {
    for (const w of walls) {
      const x1 = Number(w.x1)
      const y1 = Number(w.y1)
      const x2 = Number(w.x2)
      const y2 = Number(w.y2)
      const dx = x2 - x1
      const dy = y2 - y1
      const lenSq = dx * dx + dy * dy
      if (lenSq > 0) {
        let t = ((curX - x1) * dx + (curY - y1) * dy) / lenSq
        t = Math.max(0, Math.min(1, t))
        const projX = x1 + t * dx
        const projY = y1 + t * dy
        const dist = Math.hypot(curX - projX, curY - projY)
        const thick = Number(w.thickness || 6)
        if (dist < thick / 2 + 6) {
          const angle = dist > 0.1 ? Math.atan2(curY - projY, curX - projX) : (Math.PI / 2)
          curX = Math.round(projX + (thick / 2 + 12) * Math.cos(angle))
          curY = Math.round(projY + (thick / 2 + 12) * Math.sin(angle))
        }
      }
    }
  }

  // Финальное удержание внутри общих границ этажа
  curX = Math.max(bounds.minX + margin, Math.min(bounds.maxX - margin, curX))
  curY = Math.max(bounds.minY + margin, Math.min(bounds.maxY - margin, curY))

  return { x: curX, y: curY }
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
    minZoom: -3,
    maxZoom: 3,
    zoomSnap: 0.25,
    attributionControl: false,
    zoomControl: false,
  })
  map.dragging.enable()

  layoutGroup = L.layerGroup().addTo(map)
  markerGroup = L.layerGroup().addTo(map)
  routeEndpointsGroup = L.layerGroup().addTo(map)

  map.on('click', (e) => {
    const rawX = Math.round(e.latlng.lng)
    const rawY = Math.round(e.latlng.lat)
    const bounds = getFloorNavigableBounds(props.floor)

    // Игнорируем клики в далекой темной пустоте за границами пространства
    if (
      rawX < bounds.minX - 400 ||
      rawX > bounds.maxX + 400 ||
      rawY < bounds.minY - 400 ||
      rawY > bounds.maxY + 400
    ) {
      return
    }

    const snapped = snapPointToNavigable(rawX, rawY)
    emit('mapClick', {
      x: snapped.x,
      y: snapped.y,
      floor_id: props.floor.id,
    })
  })

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
  if (layoutGroup) {
    layoutGroup.clearLayers()
  }

  const rot = (props.floor.layout_data as any)?.blueprint_rotation || 0
  const isSwapped = rot === 90 || rot === 270
  const origH = props.floor.height || (props.floor as any).height_px || 900
  const origW = props.floor.width || (props.floor as any).width_px || 1400
  const floorHeight = isSwapped ? origW : origH
  const floorWidth = isSwapped ? origH : origW
  const bounds: L.LatLngBoundsExpression = [
    [0, 0],
    [floorHeight, floorWidth],
  ]

  // Свободное панорамирование без жесткой блокировки камеры leafleat setMaxBounds
  map.setMaxBounds(null as any)

  // Фоновая подложка чертежа (если загружена)
  const rawPlanUrl = props.floor.plan_image_url || (props.floor as any).plan_url
  if (rawPlanUrl) {
    const resolvedUrl = resolveMediaUrl(rawPlanUrl)
    const op = props.blueprintOpacity !== undefined ? props.blueprintOpacity : 0.85
    getRotatedPlanUrl(resolvedUrl, rot).then((displayUrl) => {
      if (currentOverlay && map) {
        map.removeLayer(currentOverlay)
      }
      currentOverlay = L.imageOverlay(displayUrl, bounds, { opacity: op }).addTo(map)
    })
  }

  // Отрисовка 2D-векторных элементов карты (комнаты, стены, препятствия, коридоры)
  if (layoutGroup && props.floor.layout_data) {
    const layout = props.floor.layout_data
    // 1. Комнаты
    if (Array.isArray(layout.rooms)) {
      layout.rooms.forEach((r: any) => {
        let shape: any
        let center: [number, number]
        if (r.points && Array.isArray(r.points) && r.points.length >= 3) {
          const latlngs: [number, number][] = r.points.map((pt: any) => [Number(pt[1]), Number(pt[0])])
          shape = L.polygon(latlngs, {
            color: r.color || '#3b82f6',
            weight: 1.5,
            fillColor: r.color || '#1e293b',
            fillOpacity: 0.2,
          })
          const avgY = latlngs.reduce((sum, p) => sum + p[0], 0) / latlngs.length
          const avgX = latlngs.reduce((sum, p) => sum + p[1], 0) / latlngs.length
          center = [avgY, avgX]
        } else {
          const p1: [number, number] = [r.y, r.x]
          const p2: [number, number] = [r.y + r.height, r.x + r.width]
          shape = L.rectangle([p1, p2], {
            color: r.color || '#3b82f6',
            weight: 1.5,
            fillColor: r.color || '#1e293b',
            fillOpacity: 0.2,
          })
          center = [r.y + r.height / 2, r.x + r.width / 2]
        }
        layoutGroup?.addLayer(shape)

        if (r.title) {
          const labelIcon = L.divIcon({
            className: 'room-label-icon',
            html: `<div class="room-title-tag">${r.title}</div>`,
            iconSize: [0, 0],
            iconAnchor: [0, 0],
          })
          layoutGroup?.addLayer(L.marker(center, { icon: labelIcon, interactive: false }))
        }
      })
    }

    // 2. Коридоры (отрисовываются как геометрический полигон-капсула, сохраняющий истинную ширину при любом зуме)
    if (Array.isArray(layout.corridors)) {
      layout.corridors.forEach((c: any) => {
        const capsuleCoords = getCorridorPolygon(c)
        const poly = L.polygon(capsuleCoords, {
          color: 'rgba(59, 130, 246, 0.4)',
          weight: 1.5,
          fillColor: '#3b82f6',
          fillOpacity: 0.2,
          interactive: false,
        })
        layoutGroup?.addLayer(poly)
      })
    }

    // 3. Препятствия (круглые колонны и прямоугольные объекты)
    if (Array.isArray(layout.obstacles)) {
      layout.obstacles.forEach((o: any) => {
        if (o.type === 'circle') {
          const circle = L.circle([o.y, o.x], {
            radius: o.radius || 30,
            color: '#64748b',
            weight: 2,
            fillColor: '#0f172a',
            fillOpacity: 0.9,
          })
          layoutGroup?.addLayer(circle)
        } else if (o.type === 'rect') {
          const p1: [number, number] = [o.y, o.x]
          const p2: [number, number] = [o.y + o.height, o.x + o.width]
          const rect = L.rectangle([p1, p2], {
            color: '#64748b',
            weight: 2,
            fillColor: '#0f172a',
            fillOpacity: 0.9,
          })
          layoutGroup?.addLayer(rect)
        }
      })
    }

    // 4. Стены
    if (Array.isArray(layout.walls)) {
      layout.walls.forEach((w: any) => {
        const wallLine = L.polyline(
          [[w.y1, w.x1], [w.y2, w.x2]],
          { color: '#94a3b8', weight: w.thickness || 5, lineCap: 'square' }
        )
        layoutGroup?.addLayer(wallLine)
      })
    }
  }

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
    const iconSize = isSelected ? 40 : 32
    const iconWidth = 120

    const icon = L.divIcon({
      className: 'poi-custom-div-icon',
      html: createMarkerHtml(poi, isSelected),
      iconSize: [iconWidth, iconSize + 35],
      iconAnchor: [iconWidth / 2, iconSize / 2],
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

  if (!props.isRouting || !props.route || !props.route.points?.length) {
    if (props.originPoint && props.originPoint.floor_id === props.floor.id) {
      const startLatlng: [number, number] = [props.originPoint.y, props.originPoint.x]
      const startIcon = L.divIcon({
        className: 'route-start-icon',
        html: `
          <div class="relative flex flex-col items-center group cursor-grab active:cursor-grabbing">
            <div style="width: 28px; height: 28px; background-color: #10b981; border: 3px solid #ffffff; border-radius: 9999px; box-shadow: 0 0 16px rgba(16,185,129,0.9);" class="flex items-center justify-center text-white font-black text-xs select-none">
              A
            </div>
            <div class="absolute -top-7 px-2 py-0.5 rounded-md bg-slate-900/90 border border-slate-700/80 text-[10px] font-semibold text-emerald-300 pointer-events-none select-none whitespace-nowrap shadow-lg">
              Старт
            </div>
          </div>
        `,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      })
      const startMarker = L.marker(startLatlng, {
        icon: startIcon,
        draggable: true,
        zIndexOffset: 3000,
      }).addTo(routeEndpointsGroup!)

      startMarker.on('dragend', () => {
        const pos = startMarker.getLatLng()
        const rawX = Math.round(pos.lng)
        const rawY = Math.round(pos.lat)
        const snapped = snapPointToNavigable(rawX, rawY)
        startMarker.setLatLng([snapped.y, snapped.x])
        emit('updateOrigin', {
          x: snapped.x,
          y: snapped.y,
          floor_id: props.floor.id,
        })
      })
    }
    return
  }

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
  const startLatlng: [number, number] = (props.originPoint && props.originPoint.floor_id === props.floor.id)
    ? [props.originPoint.y, props.originPoint.x]
    : latlngs[0]
  const endLatlng = latlngs[latlngs.length - 1]

  const startIcon = L.divIcon({
    className: 'route-start-icon',
    html: `
      <div class="relative flex flex-col items-center group cursor-grab active:cursor-grabbing">
        <div style="width: 28px; height: 28px; background-color: #10b981; border: 3px solid #ffffff; border-radius: 9999px; box-shadow: 0 0 16px rgba(16,185,129,0.9);" class="flex items-center justify-center text-white font-black text-xs select-none">
          A
        </div>
        <div class="absolute -top-7 px-2 py-0.5 rounded-md bg-slate-900/90 border border-slate-700/80 text-[10px] font-semibold text-emerald-300 pointer-events-none select-none whitespace-nowrap shadow-lg">
          Старт (перетащите)
        </div>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })

  const endIcon = L.divIcon({
    className: 'route-end-icon',
    html: `
      <div class="relative flex flex-col items-center">
        <div style="width: 28px; height: 28px; background-color: #ef4444; border: 3px solid #ffffff; border-radius: 9999px; box-shadow: 0 0 18px rgba(239,68,68,0.9); animation: pulse 1.5s infinite;" class="flex items-center justify-center text-white font-black text-xs select-none">
          B
        </div>
        <div class="absolute -top-7 px-2 py-0.5 rounded-md bg-slate-900/90 border border-slate-700/80 text-[10px] font-semibold text-rose-300 pointer-events-none select-none whitespace-nowrap shadow-lg">
          Финиш
        </div>
      </div>
    `,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })

  const startMarker = L.marker(startLatlng, {
    icon: startIcon,
    draggable: true,
    zIndexOffset: 3000,
  }).addTo(routeEndpointsGroup!)

  startMarker.on('dragend', () => {
    const pos = startMarker.getLatLng()
    const rawX = Math.round(pos.lng)
    const rawY = Math.round(pos.lat)
    const snapped = snapPointToNavigable(rawX, rawY)
    startMarker.setLatLng([snapped.y, snapped.x])
    emit('updateOrigin', {
      x: snapped.x,
      y: snapped.y,
      floor_id: props.floor.id,
    })
  })

  L.marker(endLatlng, { icon: endIcon, zIndexOffset: 3000 }).addTo(routeEndpointsGroup!)
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

// Следим за прозрачностью подложки
watch(() => props.blueprintOpacity, (newVal) => {
  if (currentOverlay && newVal !== undefined) {
    currentOverlay.setOpacity(newVal)
  }
})

// Следим за точками интереса и выбором
watch([() => props.pois, () => props.selectedPoi], () => {
  renderMarkers()
  if (props.selectedPoi && props.selectedPoi.floor_id === props.floor.id && map) {
    const latlng = toLatLng(props.selectedPoi.x, props.selectedPoi.y, props.floor.height)
    map.panTo(latlng, { animate: true, duration: 0.4 })
  }
})

// Следим за маршрутом и точкой старта
watch([() => props.route, () => props.isRouting, () => props.originPoint], () => {
  renderRoute()
}, { deep: true })

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
    <div
      ref="mapContainer"
      class="w-full h-full select-none outline-none"
      :class="{ 'cursor-crosshair-mode': isPickingOrigin }"
    ></div>
  </div>
</template>

<style>
/* Режим выбора точки на карте */
.cursor-crosshair-mode,
.cursor-crosshair-mode .leaflet-container,
.cursor-crosshair-mode .leaflet-interactive,
.cursor-crosshair-mode .leaflet-grab {
  cursor: crosshair !important;
}

/* Стили для кастомных Leaflet divIcon */
.poi-custom-div-icon,
.route-start-icon,
.route-end-icon {
  background: transparent !important;
  border: none !important;
}

.room-label-icon {
  background: transparent !important;
  border: none !important;
  display: flex !important;
  align-items: center;
  justify-content: center;
  width: auto !important;
  height: auto !important;
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.room-title-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: max-content;
  max-width: none;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.85);
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
  white-space: nowrap;
  pointer-events: none;
  user-select: none;
}

.leaflet-container {
  background-color: #070c18 !important;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 50px 50px;
  font-family: inherit;
}

.poi-marker-wrap {
  width: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.poi-label {
  max-width: 110px;
  overflow: hidden;
  font-size: 11px;
}

.poi-label-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: normal;
  word-break: break-word;
  line-height: 1.15;
}

.poi-marker-wrap:hover .poi-label {
  max-width: max-content;
  z-index: 9999;
}

.poi-marker-wrap:hover .poi-label-text {
  -webkit-line-clamp: unset;
}
</style>
