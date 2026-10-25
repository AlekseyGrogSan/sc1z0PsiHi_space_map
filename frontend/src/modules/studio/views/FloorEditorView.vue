<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { floorsApi, poisApi, navApi, spacesApi } from '../../../api'
import { resolveMediaUrl } from '../../../api/client'
import FloorSidebar from '../components/FloorSidebar.vue'
import PlanUploadPanel from '../components/PlanUploadPanel.vue'
import AddPoiModal from '../components/AddPoiModal.vue'
import AddPanoramaModal from '../components/AddPanoramaModal.vue'
import {
  ArrowLeft, Layers, Trash2, Check, X, Square, Minus, Circle, Box,
  Footprints, MapPin, Zap, Eye, RotateCcw, Copy, Ruler, Shapes, Wand2, Magnet, Camera
} from 'lucide-vue-next'

const props = defineProps({ spaceId: String, floorId: String })
const router = useRouter()

// State
const space = ref(null)
const floors = ref([])
const currentFloor = ref(null)
const pois = ref([])
const navNodes = ref([])
const navEdges = ref([])
const layoutData = ref({ rooms: [], walls: [], obstacles: [], corridors: [] })
const loading = ref(true)
const mode = ref('view') // 'view' | 'room' | 'poly-room' | 'wall' | 'circle' | 'rect' | 'corridor' | 'poi' | 'panorama'
const showUpload = ref(false)
const addPoiModal = ref(null) // { x, y } in pixel coords
const addPanoramaModal = ref(null) // { x, y } in pixel coords
const addRoomModal = ref(null) // { p1, p2, points, title, color }
const addCircleModal = ref(null) // { lat, lng, radius, title }
const selectedElement = ref(null) // { type, item }
const drawingPoint = ref(null) // { lat, lng } start point for 2-click drawing
const polyPoints = ref([]) // [{ lat, lng }] points for polygon room drawing
const corridorWidth = ref(35) // Width of corridor in px
const isMobileSidebarOpen = ref(false) // Mobile tools drawer state

// Blueprint & Graph options
const blueprintOpacity = ref(0.85)
const blueprintRotation = ref(0)
const showGraph = ref(false)
const generatingGraph = ref(false)
const savingLayout = ref(false)
const isGraphDirty = ref(false)
const graphStats = ref({ nodes: 0, edges: 0 })

// Calibration
const calibrating = ref(false)
const calibResult = ref(null)
const calibDistance = ref('')
let calibPoints = []

// Leaflet
let map = null
let overlayLayer = null
let roomsLayer = null
let wallsLayer = null
let obstaclesLayer = null
let corridorsLayer = null
let poisLayer = null
let handlesLayer = null
let graphLayer = null
let previewLayer = null
let calibLayer = null
let isDraggingShape = false
let justDragged = false
const mapReady = ref(false)

const layoutCounts = computed(() => ({
  rooms: layoutData.value.rooms?.length || 0,
  walls: layoutData.value.walls?.length || 0,
  obstacles: layoutData.value.obstacles?.length || 0,
  corridors: layoutData.value.corridors?.length || 0,
  pois: pois.value?.length || 0,
}))

async function fetchData() {
  loading.value = true
  try {
    const { data: spaceData } = await spacesApi.get(props.spaceId)
    space.value = spaceData
    floors.value = Array.isArray(spaceData?.floors) ? spaceData.floors : []
    currentFloor.value = floors.value.find(f => String(f.id) === String(props.floorId)) || floors.value[0]
    if (currentFloor.value) {
      await loadFloorData()
    }
  } catch (e) {
    console.error('Ошибка загрузки пространства:', e)
  } finally {
    loading.value = false
  }
}

async function loadFloorData() {
  if (!currentFloor.value) return
  const fid = currentFloor.value.id

  // Load layout_data
  layoutData.value = {
    rooms: currentFloor.value.layout_data?.rooms || [],
    walls: currentFloor.value.layout_data?.walls || [],
    obstacles: currentFloor.value.layout_data?.obstacles || [],
    corridors: currentFloor.value.layout_data?.corridors || [],
    blueprint_rotation: currentFloor.value.layout_data?.blueprint_rotation || 0,
  }
  blueprintRotation.value = layoutData.value.blueprint_rotation || 0

  const [poisRes, graphRes] = await Promise.allSettled([
    poisApi.list(fid),
    navApi.getGraph(fid),
  ])

  pois.value = poisRes.status === 'fulfilled'
    ? (Array.isArray(poisRes.value.data) ? poisRes.value.data : (poisRes.value.data?.items || []))
    : []

  if (graphRes.status === 'fulfilled' && graphRes.value?.data) {
    const g = graphRes.value.data
    navNodes.value = g.nodes || []
    navEdges.value = g.edges || []
    graphStats.value = {
      nodes: navNodes.value.length,
      edges: navEdges.value.length,
    }
  } else {
    navNodes.value = []
    navEdges.value = []
    graphStats.value = { nodes: 0, edges: 0 }
  }

  if (map) refreshMapLayers()
}

// Rotate image overlay via offscreen canvas
function getRotatedPlanUrl(imageUrl, degrees) {
  const normDeg = ((degrees % 360) + 360) % 360
  if (normDeg === 0) return Promise.resolve(imageUrl)

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
        console.warn('Canvas rotation fallback:', e)
        resolve(imageUrl)
      }
    }
    img.onerror = () => resolve(imageUrl)
    img.src = imageUrl
  })
}

// Leaflet Map Initialization
async function initMap() {
  const L = (await import('leaflet')).default
  await import('leaflet/dist/leaflet.css')
  window.L = L

  if (map) {
    map.remove()
    map = null
  }

  const floor = currentFloor.value
  blueprintRotation.value = floor?.layout_data?.blueprint_rotation || 0
  const rawPlanUrl = resolveMediaUrl(floor?.plan_url || floor?.plan_image_url)
  const isSwapped = blueprintRotation.value === 90 || blueprintRotation.value === 270
  const origW = floor?.width_px || floor?.width || 1400
  const origH = floor?.height_px || floor?.height || 900
  const w = isSwapped ? origH : origW
  const h = isSwapped ? origW : origH

  map = L.map('floor-map', {
    crs: L.CRS.Simple,
    minZoom: -3,
    maxZoom: 3,
    zoomSnap: 0.25,
    attributionControl: false,
    doubleClickZoom: false,
  })

  const bounds = [[0, 0], [h, w]]

  if (rawPlanUrl) {
    const displayUrl = await getRotatedPlanUrl(rawPlanUrl, blueprintRotation.value)
    overlayLayer = L.imageOverlay(displayUrl, bounds, { opacity: blueprintOpacity.value }).addTo(map)
  }

  roomsLayer = L.layerGroup().addTo(map)
  corridorsLayer = L.layerGroup().addTo(map)
  obstaclesLayer = L.layerGroup().addTo(map)
  wallsLayer = L.layerGroup().addTo(map)
  poisLayer = L.layerGroup().addTo(map)
  handlesLayer = L.layerGroup().addTo(map)
  graphLayer = L.layerGroup().addTo(map)
  previewLayer = L.layerGroup().addTo(map)
  calibLayer = L.layerGroup().addTo(map)

  map.fitBounds(bounds)
  map.on('click', onMapClick)
  map.on('mousemove', onMapMouseMove)
  map.on('dblclick', onMapDblClick)

  mapReady.value = true
  refreshMapLayers()
}

function refreshMapLayers() {
  if (!map || !window.L) return
  drawRooms()
  drawCorridors()
  drawObstacles()
  drawWalls()
  drawPois()
  drawSelectionHandles()
  drawNavGraph()
}

// Shape dragging helper with Leaflet CRS.Simple coordinates
function attachShapeDrag(layer, { onDrag, onDragEnd, onClick }) {
  let startLatLng = null
  let hasMoved = false

  layer.on('mousedown', (e) => {
    if (mode.value !== 'view') return
    window.L.DomEvent.stopPropagation(e)
    isDraggingShape = true
    hasMoved = false
    startLatLng = e.latlng
    map.dragging.disable()

    const onMouseMove = (moveEvent) => {
      if (!isDraggingShape || !startLatLng) return
      const currentLatLng = moveEvent.latlng
      const dx = currentLatLng.lng - startLatLng.lng
      const dy = currentLatLng.lat - startLatLng.lat
      if (!hasMoved && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
        hasMoved = true
      }
      if (hasMoved && onDrag) {
        onDrag(Math.round(dx), Math.round(dy))
      }
    }

    const onMouseUp = (upEvent) => {
      if (!isDraggingShape) return
      isDraggingShape = false
      map.dragging.enable()
      map.off('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)

      if (hasMoved) {
        justDragged = true
        setTimeout(() => { justDragged = false }, 120)
        const currentLatLng = upEvent.latlng || (map ? map.mouseEventToLatLng(upEvent) : null)
        const dx = currentLatLng ? (currentLatLng.lng - startLatLng.lng) : 0
        const dy = currentLatLng ? (currentLatLng.lat - startLatLng.lat) : 0
        if (onDragEnd) onDragEnd(Math.round(dx), Math.round(dy))
      }
    }

    map.on('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  })

  layer.on('click', (e) => {
    if (calibrating.value) {
      window.L.DomEvent.stopPropagation(e)
      handleCalibClick(e.latlng.lat, e.latlng.lng)
      return
    }
    if (mode.value !== 'view') return
    window.L.DomEvent.stopPropagation(e)
    if (justDragged) return
    if (onClick) onClick(e)
  })
}

// 1. Draw Rooms (Draggable, supports both rectangular and polygon rooms)
function drawRooms() {
  if (!roomsLayer || !window.L) return
  roomsLayer.clearLayers()
  const L = window.L

  const rooms = layoutData.value.rooms || []
  rooms.forEach(r => {
    const isSel = selectedElement.value?.type === 'room' && selectedElement.value?.item?.id === r.id
    const hasPoly = r.points && Array.isArray(r.points) && r.points.length >= 3
    let shape
    let center

    if (hasPoly) {
      const latlngs = r.points.map(pt => [Number(pt[1]), Number(pt[0])])
      shape = L.polygon(latlngs, {
        color: isSel ? '#ffffff' : (r.color || '#6366f1'),
        weight: isSel ? 3 : 1.5,
        dashArray: isSel ? '4, 4' : null,
        fillColor: r.color || '#6366f1',
        fillOpacity: isSel ? 0.35 : 0.2,
        className: 'element-draggable',
      })

      const avgY = latlngs.reduce((sum, p) => sum + p[0], 0) / latlngs.length
      const avgX = latlngs.reduce((sum, p) => sum + p[1], 0) / latlngs.length
      center = [avgY, avgX]

      const origPoints = r.points.map(p => [p[0], p[1]])
      attachShapeDrag(shape, {
        onDrag: (dx, dy) => {
          shape.setLatLngs(origPoints.map(p => [p[1] + dy, p[0] + dx]))
        },
        onDragEnd: async (dx, dy) => {
          r.points = origPoints.map(p => [Math.round(p[0] + dx), Math.round(p[1] + dy)])
          const xs = r.points.map(p => p[0])
          const ys = r.points.map(p => p[1])
          r.x = Math.min(...xs)
          r.y = Math.min(...ys)
          r.width = Math.max(...xs) - r.x
          r.height = Math.max(...ys) - r.y
          selectedElement.value = { type: 'room', item: r }
          await saveLayoutData(false)
        },
        onClick: () => {
          selectedElement.value = { type: 'room', item: r }
          refreshMapLayers()
        },
      })
    } else {
      const p1 = [r.y, r.x]
      const p2 = [r.y + r.height, r.x + r.width]
      shape = L.rectangle([p1, p2], {
        color: isSel ? '#ffffff' : (r.color || '#3b82f6'),
        weight: isSel ? 3 : 1.5,
        dashArray: isSel ? '4, 4' : null,
        fillColor: r.color || '#3b82f6',
        fillOpacity: isSel ? 0.35 : 0.2,
        className: 'element-draggable',
      })
      center = [r.y + r.height / 2, r.x + r.width / 2]
      const origX = r.x
      const origY = r.y
      const origW = r.width
      const origH = r.height

      attachShapeDrag(shape, {
        onDrag: (dx, dy) => {
          shape.setBounds([[origY + dy, origX + dx], [origY + origH + dy, origX + origW + dx]])
        },
        onDragEnd: async (dx, dy) => {
          r.x = Math.round(origX + dx)
          r.y = Math.round(origY + dy)
          selectedElement.value = { type: 'room', item: r }
          await saveLayoutData(false)
        },
        onClick: () => {
          selectedElement.value = { type: 'room', item: r }
          refreshMapLayers()
        },
      })
    }

    roomsLayer.addLayer(shape)

    if (r.title && center) {
      const label = L.divIcon({
        className: 'room-label-badge',
        html: `<div class="room-title-tag ${isSel ? 'selected' : ''}">${r.title}</div>`,
        iconSize: [0, 0],
        iconAnchor: [0, 0],
      })
      roomsLayer.addLayer(L.marker(center, { icon: label, interactive: false }))
    }
  })
}

function getCorridorPolygon(c) {
  const x1 = Number(c.x1)
  const y1 = Number(c.y1)
  const x2 = Number(c.x2)
  const y2 = Number(c.y2)
  const r = (Number(c.width) || 24) / 2.0
  const dx = x2 - x1
  const dy = y2 - y1
  const len = Math.hypot(dx, dy)

  const pts = []
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

// 2. Draw Corridors (Draggable, scales with map coordinates upon zoom)
function drawCorridors() {
  if (!corridorsLayer || !window.L) return
  corridorsLayer.clearLayers()
  const L = window.L

  const corridors = layoutData.value.corridors || []
  corridors.forEach(c => {
    const isSel = selectedElement.value?.type === 'corridor' && selectedElement.value?.item?.id === c.id
    const capsuleCoords = getCorridorPolygon(c)
    const poly = L.polygon(capsuleCoords, {
      color: isSel ? '#34d399' : 'rgba(59, 130, 246, 0.5)',
      weight: isSel ? 2.5 : 1.5,
      dashArray: isSel ? '4, 4' : null,
      fillColor: isSel ? '#10b981' : '#3b82f6',
      fillOpacity: isSel ? 0.35 : 0.22,
      className: 'element-draggable',
    })

    const spine = L.polyline(
      [[c.y1, c.x1], [c.y2, c.x2]],
      {
        color: isSel ? '#10b981' : 'rgba(96, 165, 250, 0.7)',
        weight: 2,
        dashArray: '4, 4',
        interactive: false,
      }
    )

    const origX1 = c.x1
    const origY1 = c.y1
    const origX2 = c.x2
    const origY2 = c.y2

    attachShapeDrag(poly, {
      onDrag: (dx, dy) => {
        const movedC = { ...c, x1: origX1 + dx, y1: origY1 + dy, x2: origX2 + dx, y2: origY2 + dy }
        poly.setLatLngs(getCorridorPolygon(movedC))
        spine.setLatLngs([[origY1 + dy, origX1 + dx], [origY2 + dy, origX2 + dx]])
      },
      onDragEnd: async (dx, dy) => {
        c.x1 = Math.round(origX1 + dx)
        c.y1 = Math.round(origY1 + dy)
        c.x2 = Math.round(origX2 + dx)
        c.y2 = Math.round(origY2 + dy)
        selectedElement.value = { type: 'corridor', item: c }
        await saveLayoutData(false)
      },
      onClick: () => {
        selectedElement.value = { type: 'corridor', item: c }
        refreshMapLayers()
      },
    })
    corridorsLayer.addLayer(poly)
    corridorsLayer.addLayer(spine)
  })
}

// 3. Draw Obstacles (Circular columns and rectangular booths, Draggable)
function drawObstacles() {
  if (!obstaclesLayer || !window.L) return
  obstaclesLayer.clearLayers()
  const L = window.L

  const obstacles = layoutData.value.obstacles || []
  obstacles.forEach(o => {
    const isSel = selectedElement.value?.type === 'obstacle' && selectedElement.value?.item?.id === o.id
    if (o.type === 'circle') {
      const circle = L.circle([o.y, o.x], {
        radius: o.radius || 30,
        color: isSel ? '#ffffff' : '#64748b',
        weight: isSel ? 3 : 2,
        fillColor: '#1e293b',
        fillOpacity: 0.9,
        className: 'element-draggable',
      })
      const origX = o.x
      const origY = o.y

      attachShapeDrag(circle, {
        onDrag: (dx, dy) => {
          circle.setLatLng([origY + dy, origX + dx])
        },
        onDragEnd: async (dx, dy) => {
          o.x = Math.round(origX + dx)
          o.y = Math.round(origY + dy)
          selectedElement.value = { type: 'obstacle', item: o }
          await saveLayoutData(false)
        },
        onClick: () => {
          selectedElement.value = { type: 'obstacle', item: o }
          refreshMapLayers()
        },
      })
      obstaclesLayer.addLayer(circle)

      if (o.title) {
        const label = L.divIcon({
          className: 'obstacle-label-badge',
          html: `<div class="obstacle-tag">${o.title}</div>`,
          iconSize: [0, 0],
          iconAnchor: [0, 0],
        })
        obstaclesLayer.addLayer(L.marker([o.y, o.x], { icon: label, interactive: false }))
      }
    } else if (o.type === 'rect') {
      const p1 = [o.y, o.x]
      const p2 = [o.y + o.height, o.x + o.width]
      const rect = L.rectangle([p1, p2], {
        color: isSel ? '#ffffff' : '#64748b',
        weight: isSel ? 3 : 2,
        fillColor: '#1e293b',
        fillOpacity: 0.9,
        className: 'element-draggable',
      })
      const origX = o.x
      const origY = o.y
      const origW = o.width
      const origH = o.height

      attachShapeDrag(rect, {
        onDrag: (dx, dy) => {
          rect.setBounds([[origY + dy, origX + dx], [origY + origH + dy, origX + origW + dx]])
        },
        onDragEnd: async (dx, dy) => {
          o.x = Math.round(origX + dx)
          o.y = Math.round(origY + dy)
          selectedElement.value = { type: 'obstacle', item: o }
          await saveLayoutData(false)
        },
        onClick: () => {
          selectedElement.value = { type: 'obstacle', item: o }
          refreshMapLayers()
        },
      })
      obstaclesLayer.addLayer(rect)
    }
  })
}

// 4. Draw Walls (Draggable)
function drawWalls() {
  if (!wallsLayer || !window.L) return
  wallsLayer.clearLayers()
  const L = window.L

  const walls = layoutData.value.walls || []
  walls.forEach(w => {
    const isSel = selectedElement.value?.type === 'wall' && selectedElement.value?.item?.id === w.id
    const wallLine = L.polyline(
      [[w.y1, w.x1], [w.y2, w.x2]],
      {
        color: isSel ? '#f43f5e' : '#cbd5e1',
        weight: isSel ? 8 : (w.thickness || 6),
        lineCap: 'square',
        className: 'element-draggable',
      }
    )
    const origX1 = w.x1
    const origY1 = w.y1
    const origX2 = w.x2
    const origY2 = w.y2

    attachShapeDrag(wallLine, {
      onDrag: (dx, dy) => {
        wallLine.setLatLngs([[origY1 + dy, origX1 + dx], [origY2 + dy, origX2 + dx]])
      },
      onDragEnd: async (dx, dy) => {
        w.x1 = Math.round(origX1 + dx)
        w.y1 = Math.round(origY1 + dy)
        w.x2 = Math.round(origX2 + dx)
        w.y2 = Math.round(origY2 + dy)
        selectedElement.value = { type: 'wall', item: w }
        await saveLayoutData(false)
      },
      onClick: () => {
        selectedElement.value = { type: 'wall', item: w }
        refreshMapLayers()
      },
    })
    wallsLayer.addLayer(wallLine)
  })
}

// 5. Draw POIs (Draggable)
const CATEGORY_ICONS = {
  entrance: '🚪', exit: '🚪', stand: '🏢', retail: '🛍️', entertainment: '🎮',
  stage: '🎤', food: '☕', bench: '🛋️', trash: '🗑️', wc: '🚻', wifi: '📶',
  info: 'ℹ️', custom: '⭐',
}

function drawPois() {
  if (!poisLayer || !window.L) return
  poisLayer.clearLayers()
  const L = window.L

  pois.value.forEach(poi => {
    const isSel = selectedElement.value?.type === 'poi' && selectedElement.value?.item?.id === poi.id
    const hasPano = !!poi.panorama_id
    const emoji = hasPano ? '📷' : (CATEGORY_ICONS[poi.category] || '📍')
    const poiTitle = poi.title || poi.name || ''
    const icon = L.divIcon({
      className: '',
      html: `
        <div class="poi-marker ${isSel ? 'selected' : ''} ${hasPano ? 'has-pano' : ''}" data-id="${poi.id}" title="${poiTitle}">
          <span class="poi-icon-box">${emoji}</span>
          <span class="poi-name-tag">${poiTitle}</span>
          ${hasPano ? '<span class="poi-pano-tag" style="background:#a855f7;color:white;font-size:9px;font-weight:bold;padding:1px 4px;border-radius:9999px;position:absolute;top:-6px;right:-8px;border:1px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.5);">360°</span>' : ''}
        </div>
      `,
      iconAnchor: [16, 16],
    })
    const py = Number(poi.y_coord ?? poi.y ?? 0)
    const px = Number(poi.x_coord ?? poi.x ?? 0)
    const marker = L.marker([py, px], { icon, draggable: true })

    marker.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      const b = getFloorNavigableBounds()
      const npx = Math.max(b.minX + 5, Math.min(b.maxX - 5, Math.round(lng)))
      const npy = Math.max(b.minY + 5, Math.min(b.maxY - 5, Math.round(lat)))
      poi.y_coord = npy
      poi.x_coord = npx
      poi.x = npx
      poi.y = npy
      selectedElement.value = { type: 'poi', item: poi }
      await poisApi.update(poi.id, { y_coord: npy, x_coord: npx })
      isGraphDirty.value = true
      refreshMapLayers()
    })

    marker.on('click', (e) => {
      if (mode.value === 'view') {
        L.DomEvent.stopPropagation(e)
        selectedElement.value = { type: 'poi', item: poi }
        refreshMapLayers()
      }
    })

    poisLayer.addLayer(marker)
  })
}

// 6. Draw Interactive Selection Handles for Selected Element
function createHandleIcon(color = '#3b82f6') {
  return window.L.divIcon({
    className: 'selection-handle-wrapper',
    html: `<div style="width: 14px; height: 14px; border-radius: 50%; background: ${color}; border: 2px solid #ffffff; box-shadow: 0 0 8px rgba(0,0,0,0.8); cursor: crosshair;"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

function drawSelectionHandles() {
  if (!handlesLayer || !window.L) return
  handlesLayer.clearLayers()
  if (!selectedElement.value || mode.value !== 'view') return

  const L = window.L
  const { type, item } = selectedElement.value

  if (type === 'wall') {
    const h1 = L.marker([item.y1, item.x1], { icon: createHandleIcon('#f43f5e'), draggable: true })
    h1.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      const snapped = getSnappedPoint(lat, lng, { lat: item.y2, lng: item.x2 })
      item.x1 = Math.round(snapped.lng)
      item.y1 = Math.round(snapped.lat)
      await saveLayoutData(false)
    })
    handlesLayer.addLayer(h1)

    const h2 = L.marker([item.y2, item.x2], { icon: createHandleIcon('#f43f5e'), draggable: true })
    h2.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      const snapped = getSnappedPoint(lat, lng, { lat: item.y1, lng: item.x1 })
      item.x2 = Math.round(snapped.lng)
      item.y2 = Math.round(snapped.lat)
      await saveLayoutData(false)
    })
    handlesLayer.addLayer(h2)
  } else if (type === 'corridor') {
    const h1 = L.marker([item.y1, item.x1], { icon: createHandleIcon('#10b981'), draggable: true })
    h1.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      item.x1 = Math.round(lng)
      item.y1 = Math.round(lat)
      await saveLayoutData(false)
    })
    handlesLayer.addLayer(h1)

    const h2 = L.marker([item.y2, item.x2], { icon: createHandleIcon('#10b981'), draggable: true })
    h2.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      item.x2 = Math.round(lng)
      item.y2 = Math.round(lat)
      await saveLayoutData(false)
    })
    handlesLayer.addLayer(h2)
  } else if (type === 'room') {
    if (item.points && Array.isArray(item.points) && item.points.length >= 3) {
      item.points.forEach((pt, idx) => {
        const h = L.marker([pt[1], pt[0]], { icon: createHandleIcon('#6366f1'), draggable: true })
        h.on('dragend', async (e) => {
          const { lat, lng } = e.target.getLatLng()
          const snapped = getSnappedPoint(lat, lng)
          item.points[idx] = [Math.round(snapped.lng), Math.round(snapped.lat)]
          const xs = item.points.map(p => p[0])
          const ys = item.points.map(p => p[1])
          item.x = Math.min(...xs)
          item.y = Math.min(...ys)
          item.width = Math.max(...xs) - item.x
          item.height = Math.max(...ys) - item.y
          await saveLayoutData(false)
        })
        handlesLayer.addLayer(h)
      })
    } else {
      const corners = [
        { id: 'ne', lat: item.y + item.height, lng: item.x + item.width },
        { id: 'sw', lat: item.y, lng: item.x },
      ]
      corners.forEach(c => {
        const h = L.marker([c.lat, c.lng], { icon: createHandleIcon('#3b82f6'), draggable: true })
        h.on('dragend', async (e) => {
          const { lat, lng } = e.target.getLatLng()
          const targetLng = Math.round(lng)
          const targetLat = Math.round(lat)
          if (c.id === 'ne') {
            item.width = Math.max(20, targetLng - item.x)
            item.height = Math.max(20, targetLat - item.y)
          } else {
            const oldRight = item.x + item.width
            const oldTop = item.y + item.height
            item.x = Math.min(targetLng, oldRight - 20)
            item.width = oldRight - item.x
            item.y = Math.min(targetLat, oldTop - 20)
            item.height = oldTop - item.y
          }
          await saveLayoutData(false)
        })
        handlesLayer.addLayer(h)
      })
    }
  } else if (type === 'obstacle' && item.type === 'rect') {
    const corners = [
      { id: 'ne', lat: item.y + item.height, lng: item.x + item.width },
      { id: 'sw', lat: item.y, lng: item.x },
    ]
    corners.forEach(c => {
      const h = L.marker([c.lat, c.lng], { icon: createHandleIcon('#f59e0b'), draggable: true })
      h.on('dragend', async (e) => {
        const { lat, lng } = e.target.getLatLng()
        const targetLng = Math.round(lng)
        const targetLat = Math.round(lat)
        if (c.id === 'ne') {
          item.width = Math.max(10, targetLng - item.x)
          item.height = Math.max(10, targetLat - item.y)
        } else {
          const oldRight = item.x + item.width
          const oldTop = item.y + item.height
          item.x = Math.min(targetLng, oldRight - 10)
          item.width = oldRight - item.x
          item.y = Math.min(targetLat, oldTop - 10)
          item.height = oldTop - item.y
        }
        await saveLayoutData(false)
      })
      handlesLayer.addLayer(h)
    })
  } else if (type === 'obstacle' && item.type === 'circle') {
    const edgeLat = item.y
    const edgeLng = item.x + (item.radius || 30)
    const rh = L.marker([edgeLat, edgeLng], { icon: createHandleIcon('#06b6d4'), draggable: true })
    rh.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      const dx = lng - item.x
      const dy = lat - item.y
      item.radius = Math.max(10, Math.round(Math.sqrt(dx * dx + dy * dy)))
      await saveLayoutData(false)
    })
    handlesLayer.addLayer(rh)
  }
}

// 6. Draw Auto-Generated Navigation Graph (Nodes & Edges)
function drawNavGraph() {
  if (!graphLayer || !window.L) return
  graphLayer.clearLayers()
  if (!showGraph.value) return

  const L = window.L

  // Edges
  navEdges.value.forEach(edge => {
    const fn = navNodes.value.find(n => n.id === edge.from_node_id || (edge.from_ref && n.ref === edge.from_ref))
    const tn = navNodes.value.find(n => n.id === edge.to_node_id || (edge.to_ref && n.ref === edge.to_ref))
    if (!fn || !tn) return

    const line = L.polyline(
      [[fn.y, fn.x], [tn.y, tn.x]],
      { color: '#60a5fa', weight: 1.5, opacity: 0.65, dashArray: '4, 4' }
    )
    graphLayer.addLayer(line)
  })

  // Nodes
  navNodes.value.forEach(n => {
    const isDoor = n.node_type === 'door'
    const color = isDoor ? '#10b981' : '#3b82f6'
    const dot = L.circleMarker([n.y, n.x], {
      radius: isDoor ? 5 : 3.5,
      color: '#ffffff',
      weight: 1,
      fillColor: color,
      fillOpacity: 0.9,
    })
    graphLayer.addLayer(dot)
  })
}

// Compute Navigable / Outer Floor Bounds
function getFloorNavigableBounds() {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  const layout = layoutData.value || {}

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

  if (Array.isArray(layout.walls)) {
    for (const w of layout.walls) {
      minX = Math.min(minX, Number(w.x1), Number(w.x2))
      maxX = Math.max(maxX, Number(w.x1), Number(w.x2))
      minY = Math.min(minY, Number(w.y1), Number(w.y2))
      maxY = Math.max(maxY, Number(w.y1), Number(w.y2))
    }
  }

  if (Array.isArray(layout.corridors)) {
    for (const c of layout.corridors) {
      const halfW = (Number(c.width) || 35) / 2
      minX = Math.min(minX, Number(c.x1) - halfW, Number(c.x2) - halfW)
      maxX = Math.max(maxX, Number(c.x1) + halfW, Number(c.x2) + halfW)
      minY = Math.min(minY, Number(c.y1) - halfW, Number(c.y2) - halfW)
      maxY = Math.max(maxY, Number(c.y1) + halfW, Number(c.y2) + halfW)
    }
  }

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

  const fw = currentFloor.value?.width || currentFloor.value?.width_px || 1600
  const fh = currentFloor.value?.height || currentFloor.value?.height_px || 900

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

// Save Layout to Backend (does NOT calculate graph automatically)
async function saveLayoutData(triggerGraph = false) {
  if (!currentFloor.value) return
  savingLayout.value = true
  isGraphDirty.value = true
  try {
    const { data: updatedFloor } = await floorsApi.saveLayout(currentFloor.value.id, layoutData.value)
    if (updatedFloor) {
      currentFloor.value.layout_data = updatedFloor.layout_data
    }
    if (triggerGraph) {
      await triggerAutoGraph(false)
    }
    refreshMapLayers()
  } catch (err) {
    console.error('Ошибка сохранения планировки:', err)
  } finally {
    savingLayout.value = false
  }
}

// Trigger Auto-Graph Generation
async function triggerAutoGraph(showSpinner = true) {
  if (!currentFloor.value) return
  if (showSpinner) generatingGraph.value = true
  try {
    const { data } = await navApi.autoGraph(currentFloor.value.id)
    if (data?.graph) {
      navNodes.value = data.graph.nodes || []
      navEdges.value = data.graph.edges || []
      graphStats.value = {
        nodes: navNodes.value.length,
        edges: navEdges.value.length,
      }
      isGraphDirty.value = false
      refreshMapLayers()
    }
  } catch (err) {
    console.error('Ошибка генерации навигационного графа:', err)
  } finally {
    if (showSpinner) generatingGraph.value = false
  }
}

// Explicit User Action: Save & Build Navigation Graph
async function handleBuildGraph() {
  await saveLayoutData(false)
  await triggerAutoGraph(true)
  isGraphDirty.value = false
}

// Snapping and Auto-Alignment Engine
function getSnappedPoint(lat, lng, referencePoint = null) {
  const snapDist = 18 // px threshold for magnetic vertex snapping
  let bestDist = snapDist
  let snappedLat = lat
  let snappedLng = lng
  let snappedToVertex = false
  let orthoSnapped = false

  // 1. Collect all existing vertices from walls and polygon points
  const endpoints = []
  for (const w of (layoutData.value.walls || [])) {
    endpoints.push({ x: w.x1, y: w.y1 })
    endpoints.push({ x: w.x2, y: w.y2 })
  }
  for (const p of polyPoints.value) {
    endpoints.push({ x: p.lng, y: p.lat })
  }
  if (drawingPoint.value) {
    endpoints.push({ x: drawingPoint.value.lng, y: drawingPoint.value.lat })
  }

  for (const ep of endpoints) {
    const dist = Math.hypot(lng - ep.x, lat - ep.y)
    if (dist < bestDist) {
      bestDist = dist
      snappedLng = ep.x
      snappedLat = ep.y
      snappedToVertex = true
    }
  }

  // 2. Orthogonal Snapping (0°, 90°, 180°, 270°) to reference point
  if (!snappedToVertex && referencePoint) {
    const dx = Math.abs(lng - referencePoint.lng)
    const dy = Math.abs(lat - referencePoint.lat)
    if (dy <= 12) {
      snappedLat = referencePoint.lat // Horizontal line
      orthoSnapped = true
    } else if (dx <= 12) {
      snappedLng = referencePoint.lng // Vertical line
      orthoSnapped = true
    }
  }

  return {
    lat: snappedLat,
    lng: snappedLng,
    snappedToVertex,
    orthoSnapped,
  }
}

function finishPolyRoom() {
  if (polyPoints.value.length < 3) return
  const points = polyPoints.value.map(p => [Math.round(p.lng), Math.round(p.lat)])
  addRoomModal.value = {
    points,
    title: 'Зона ' + ((layoutData.value.rooms?.length || 0) + 1),
    color: '#6366f1',
  }
  polyPoints.value = []
  previewLayer?.clearLayers()
}

function removeLastPolyPoint() {
  if (polyPoints.value.length > 0) {
    polyPoints.value.pop()
    previewLayer?.clearLayers()
  }
}

function cancelPolyRoom() {
  polyPoints.value = []
  previewLayer?.clearLayers()
}

function onMapDblClick(e) {
  if (window.L) window.L.DomEvent.stopPropagation(e)
  if (mode.value === 'poly-room' && polyPoints.value.length >= 3) {
    finishPolyRoom()
  }
}

// Map Interaction Handlers
function onMapClick(e) {
  if (!map) return
  if (justDragged) return
  const { lat, lng } = e.latlng

  if (calibrating.value) {
    handleCalibClick(lat, lng)
    return
  }

  if (mode.value === 'poi') {
    const b = getFloorNavigableBounds()
    const cx = Math.max(b.minX + 5, Math.min(b.maxX - 5, Math.round(lng)))
    const cy = Math.max(b.minY + 5, Math.min(b.maxY - 5, Math.round(lat)))
    addPoiModal.value = { x: cx, y: cy }
    return
  }

  if (mode.value === 'panorama') {
    const b = getFloorNavigableBounds()
    const cx = Math.max(b.minX + 5, Math.min(b.maxX - 5, Math.round(lng)))
    const cy = Math.max(b.minY + 5, Math.min(b.maxY - 5, Math.round(lat)))
    addPanoramaModal.value = { x: cx, y: cy }
    return
  }

  if (mode.value === 'circle') {
    addCircleModal.value = {
      lat,
      lng,
      radius: 30,
      title: 'Колонна ' + ((layoutData.value.obstacles?.filter(o => o.type === 'circle').length || 0) + 1),
    }
    return
  }

  if (mode.value === 'poly-room') {
    const prevPt = polyPoints.value.length > 0 ? polyPoints.value[polyPoints.value.length - 1] : null
    const snapped = getSnappedPoint(lat, lng, prevPt)

    // Check if clicked near first point to close polygon
    if (polyPoints.value.length >= 3) {
      const first = polyPoints.value[0]
      const distToStart = Math.hypot(lat - first.lat, lng - first.lng)
      if (distToStart <= 22 || (snapped.snappedToVertex && Math.abs(snapped.lat - first.lat) < 5 && Math.abs(snapped.lng - first.lng) < 5)) {
        finishPolyRoom()
        return
      }
    }

    polyPoints.value.push({ lat: snapped.lat, lng: snapped.lng })
    return
  }

  if (mode.value === 'wall') {
    const snapped = getSnappedPoint(lat, lng, drawingPoint.value)
    if (!drawingPoint.value) {
      drawingPoint.value = { lat: snapped.lat, lng: snapped.lng }
    } else {
      const p1 = drawingPoint.value
      const p2 = snapped
      if (Math.round(p1.lng) !== Math.round(p2.lng) || Math.round(p1.lat) !== Math.round(p2.lat)) {
        const newWall = {
          id: 'w_' + Date.now(),
          x1: Math.round(p1.lng),
          y1: Math.round(p1.lat),
          x2: Math.round(p2.lng),
          y2: Math.round(p2.lat),
          thickness: 6,
        }
        layoutData.value.walls = [...(layoutData.value.walls || []), newWall]
        saveLayoutData()
      }
      drawingPoint.value = null
      previewLayer?.clearLayers()
    }
    return
  }

  if (mode.value === 'corridor') {
    if (!drawingPoint.value) {
      drawingPoint.value = { lat, lng }
    } else {
      const p1 = drawingPoint.value
      const p2 = { lat, lng }
      const newCorr = {
        id: 'c_' + Date.now(),
        x1: Math.round(p1.lng),
        y1: Math.round(p1.lat),
        x2: Math.round(p2.lng),
        y2: Math.round(p2.lat),
        width: Number(corridorWidth.value) || 35,
      }
      layoutData.value.corridors = [...(layoutData.value.corridors || []), newCorr]
      drawingPoint.value = null
      previewLayer?.clearLayers()
      saveLayoutData()
    }
    return
  }

  if (mode.value === 'rect') {
    if (!drawingPoint.value) {
      drawingPoint.value = { lat, lng }
    } else {
      const p1 = drawingPoint.value
      const p2 = { lat, lng }
      const minX = Math.round(Math.min(p1.lng, p2.lng))
      const maxX = Math.round(Math.max(p1.lng, p2.lng))
      const minY = Math.round(Math.min(p1.lat, p2.lat))
      const maxY = Math.round(Math.max(p1.lat, p2.lat))
      const newRect = {
        id: 'o_' + Date.now(),
        type: 'rect',
        title: 'Препятствие',
        x: minX,
        y: minY,
        width: Math.max(10, maxX - minX),
        height: Math.max(10, maxY - minY),
      }
      layoutData.value.obstacles = [...(layoutData.value.obstacles || []), newRect]
      drawingPoint.value = null
      previewLayer?.clearLayers()
      saveLayoutData()
    }
    return
  }

  if (mode.value === 'room') {
    if (!drawingPoint.value) {
      drawingPoint.value = { lat, lng }
    } else {
      addRoomModal.value = {
        p1: drawingPoint.value,
        p2: { lat, lng },
        title: 'Зона ' + ((layoutData.value.rooms?.length || 0) + 1),
        color: '#3b82f6',
      }
      drawingPoint.value = null
      previewLayer?.clearLayers()
    }
    return
  }

  if (mode.value === 'view') {
    selectedElement.value = null
    refreshMapLayers()
  }
}

function onMapMouseMove(e) {
  if (!previewLayer || !window.L) return
  const L = window.L
  const { lat, lng } = e.latlng

  if (mode.value === 'poly-room') {
    previewLayer.clearLayers()
    if (polyPoints.value.length === 0) return

    const lastPt = polyPoints.value[polyPoints.value.length - 1]
    const snapped = getSnappedPoint(lat, lng, lastPt)
    const pts = [...polyPoints.value.map(p => [p.lat, p.lng]), [snapped.lat, snapped.lng]]

    if (pts.length >= 3) {
      L.polygon(pts, {
        color: '#6366f1',
        weight: 2,
        dashArray: '5, 5',
        fillColor: '#818cf8',
        fillOpacity: 0.25,
      }).addTo(previewLayer)
    } else {
      L.polyline(pts, {
        color: '#6366f1',
        weight: 2,
        dashArray: '5, 5',
      }).addTo(previewLayer)
    }

    polyPoints.value.forEach((p, idx) => {
      const isStart = idx === 0
      L.circleMarker([p.lat, p.lng], {
        radius: isStart ? 6 : 4,
        color: isStart ? '#10b981' : '#6366f1',
        fillColor: '#ffffff',
        fillOpacity: 1,
        weight: 2,
      }).addTo(previewLayer)
    })

    if (polyPoints.value.length >= 3) {
      const first = polyPoints.value[0]
      if (Math.hypot(lat - first.lat, lng - first.lng) <= 22) {
        L.circleMarker([first.lat, first.lng], {
          radius: 10,
          color: '#10b981',
          fillColor: '#10b981',
          fillOpacity: 0.5,
          weight: 2,
        }).addTo(previewLayer)
      }
    }
    return
  }

  if (!drawingPoint.value) return
  previewLayer.clearLayers()
  const p1 = drawingPoint.value
  const snapped = getSnappedPoint(lat, lng, p1)
  const p2 = snapped

  if (mode.value === 'wall') {
    L.polyline([[p1.lat, p1.lng], [p2.lat, p2.lng]], {
      color: '#cbd5e1',
      weight: 6,
      dashArray: '6, 6',
    }).addTo(previewLayer)

    if (snapped.snappedToVertex) {
      L.circleMarker([p2.lat, p2.lng], {
        radius: 7,
        color: '#10b981',
        fillColor: '#34d399',
        fillOpacity: 0.8,
        weight: 2,
      }).addTo(previewLayer)
    } else if (snapped.orthoSnapped) {
      L.circleMarker([p2.lat, p2.lng], {
        radius: 5,
        color: '#60a5fa',
        fillColor: '#3b82f6',
        fillOpacity: 0.8,
        weight: 1.5,
      }).addTo(previewLayer)
    }
  } else if (mode.value === 'corridor') {
    L.polyline([[p1.lat, p1.lng], [p2.lat, p2.lng]], {
      color: 'rgba(59, 130, 246, 0.4)',
      weight: Number(corridorWidth.value) || 35,
      lineCap: 'round',
    }).addTo(previewLayer)
  } else if (mode.value === 'room') {
    L.rectangle([[p1.lat, p1.lng], [p2.lat, p2.lng]], {
      color: '#3b82f6',
      weight: 2,
      dashArray: '4, 4',
      fillColor: '#3b82f6',
      fillOpacity: 0.15,
    }).addTo(previewLayer)
  } else if (mode.value === 'rect') {
    L.rectangle([[p1.lat, p1.lng], [p2.lat, p2.lng]], {
      color: '#f59e0b',
      weight: 2,
      dashArray: '4, 4',
      fillColor: '#f59e0b',
      fillOpacity: 0.25,
    }).addTo(previewLayer)
  }
}

function cancelDrawing() {
  drawingPoint.value = null
  cancelPolyRoom()
  previewLayer?.clearLayers()
}

// Modal Confirmations
function confirmAddRoom() {
  if (!addRoomModal.value) return
  const { p1, p2, points, title, color } = addRoomModal.value
  let roomData = null

  if (points && Array.isArray(points) && points.length >= 3) {
    const xs = points.map(p => Number(p[0]))
    const ys = points.map(p => Number(p[1]))
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    roomData = {
      id: 'r_' + Date.now(),
      title: title || 'Зона',
      color: color || '#6366f1',
      points: points.map(p => [Math.round(p[0]), Math.round(p[1])]),
      x: minX,
      y: minY,
      width: Math.max(10, maxX - minX),
      height: Math.max(10, maxY - minY),
    }
  } else if (p1 && p2) {
    const minX = Math.round(Math.min(p1.lng, p2.lng))
    const maxX = Math.round(Math.max(p1.lng, p2.lng))
    const minY = Math.round(Math.min(p1.lat, p2.lat))
    const maxY = Math.round(Math.max(p1.lat, p2.lat))
    roomData = {
      id: 'r_' + Date.now(),
      title: title || 'Зона',
      color: color || '#3b82f6',
      x: minX,
      y: minY,
      width: Math.max(10, maxX - minX),
      height: Math.max(10, maxY - minY),
    }
  }

  if (roomData) {
    layoutData.value.rooms = [...(layoutData.value.rooms || []), roomData]
  }
  addRoomModal.value = null
  saveLayoutData()
}

// Alignment & Straightening of Walls
function alignAndMergeWalls(showNotification = true) {
  const walls = layoutData.value.walls || []
  if (walls.length < 2) return

  let alignedCount = 0
  let gluedCount = 0
  let mergedCount = 0

  // 1. Orthogonalize walls nearly aligned with horizontal/vertical axes (within 8 deg)
  const orthoWalls = walls.map(w => {
    let { x1, y1, x2, y2 } = w
    const dx = x2 - x1
    const dy = y2 - y1
    const len = Math.hypot(dx, dy)
    if (len < 4) return { ...w }
    const angle = (Math.abs(Math.atan2(dy, dx)) * 180) / Math.PI

    if (angle <= 8 || angle >= 172) {
      const avgY = Math.round((y1 + y2) / 2)
      if (y1 !== avgY || y2 !== avgY) alignedCount++
      y1 = avgY
      y2 = avgY
    } else if (angle >= 82 && angle <= 98) {
      const avgX = Math.round((x1 + x2) / 2)
      if (x1 !== avgX || x2 !== avgX) alignedCount++
      x1 = avgX
      x2 = avgX
    }
    return { ...w, x1, y1, x2, y2 }
  })

  // 2. Endpoint clustering & gluing (tolerance <= 18px) using Disjoint Set Union
  const snapTol = 18
  const pts = []
  orthoWalls.forEach((w, idx) => {
    pts.push({ id: `w_${idx}_1`, x: w.x1, y: w.y1, wIdx: idx, ep: 1 })
    pts.push({ id: `w_${idx}_2`, x: w.x2, y: w.y2, wIdx: idx, ep: 2 })
  })

  const parent = pts.map((_, i) => i)
  function findRoot(i) {
    if (parent[i] === i) return i
    parent[i] = findRoot(parent[i])
    return parent[i]
  }
  function union(i, j) {
    const rootI = findRoot(i)
    const rootJ = findRoot(j)
    if (rootI !== rootJ) parent[rootI] = rootJ
  }

  for (let i = 0; i < pts.length; i++) {
    for (let j = i + 1; j < pts.length; j++) {
      if (Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y) <= snapTol) {
        union(i, j)
      }
    }
  }

  const clusters = new Map()
  pts.forEach((pt, idx) => {
    const root = findRoot(idx)
    if (!clusters.has(root)) clusters.set(root, [])
    clusters.get(root).push(pt)
  })

  const gluedMap = new Map()
  clusters.forEach(clusterList => {
    if (clusterList.length > 1) gluedCount += (clusterList.length - 1)
    const avgX = Math.round(clusterList.reduce((sum, p) => sum + p.x, 0) / clusterList.length)
    const avgY = Math.round(clusterList.reduce((sum, p) => sum + p.y, 0) / clusterList.length)
    clusterList.forEach(p => gluedMap.set(p.id, { x: avgX, y: avgY }))
  })

  let updatedWalls = orthoWalls.map((w, idx) => {
    const p1 = gluedMap.get(`w_${idx}_1`) || { x: w.x1, y: w.y1 }
    const p2 = gluedMap.get(`w_${idx}_2`) || { x: w.x2, y: w.y2 }
    return { ...w, x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y }
  })

  // 3. Remove zero-length walls
  updatedWalls = updatedWalls.filter(w => Math.hypot(w.x2 - w.x1, w.y2 - w.y1) >= 5)

  // 4. Merge collinear contiguous wall segments where degree == 2
  let changed = true
  while (changed) {
    changed = false
    const ptCount = new Map()
    const key = (x, y) => `${x},${y}`
    updatedWalls.forEach(w => {
      const k1 = key(w.x1, w.y1)
      const k2 = key(w.x2, w.y2)
      ptCount.set(k1, (ptCount.get(k1) || 0) + 1)
      ptCount.set(k2, (ptCount.get(k2) || 0) + 1)
    })

    for (let i = 0; i < updatedWalls.length; i++) {
      const w1 = updatedWalls[i]
      for (let j = i + 1; j < updatedWalls.length; j++) {
        const w2 = updatedWalls[j]
        let shared = null
        let A = null
        let C = null

        if (w1.x2 === w2.x1 && w1.y2 === w2.y1) {
          shared = { x: w1.x2, y: w1.y2 }
          A = { x: w1.x1, y: w1.y1 }
          C = { x: w2.x2, y: w2.y2 }
        } else if (w1.x2 === w2.x2 && w1.y2 === w2.y2) {
          shared = { x: w1.x2, y: w1.y2 }
          A = { x: w1.x1, y: w1.y1 }
          C = { x: w2.x1, y: w2.y1 }
        } else if (w1.x1 === w2.x1 && w1.y1 === w2.y1) {
          shared = { x: w1.x1, y: w1.y1 }
          A = { x: w1.x2, y: w1.y2 }
          C = { x: w2.x2, y: w2.y2 }
        } else if (w1.x1 === w2.x2 && w1.y1 === w2.y2) {
          shared = { x: w1.x1, y: w1.y1 }
          A = { x: w1.x2, y: w1.y2 }
          C = { x: w2.x1, y: w2.y1 }
        }

        if (shared && ptCount.get(key(shared.x, shared.y)) === 2) {
          const v1x = shared.x - A.x
          const v1y = shared.y - A.y
          const v2x = C.x - shared.x
          const v2y = C.y - shared.y
          const cross = v1x * v2y - v1y * v2x
          const dot = v1x * v2x + v1y * v2y
          const len1 = Math.hypot(v1x, v1y)
          const len2 = Math.hypot(v2x, v2y)

          if (len1 > 0 && len2 > 0 && Math.abs(cross) / (len1 * len2) < 0.08 && dot > 0) {
            const mergedWall = { ...w1, x1: A.x, y1: A.y, x2: C.x, y2: C.y }
            updatedWalls.splice(j, 1)
            updatedWalls[i] = mergedWall
            mergedCount++
            changed = true
            break
          }
        }
      }
      if (changed) break
    }
  }

  layoutData.value.walls = updatedWalls
  saveLayoutData()
  if (showNotification) {
    alert(`🪄 Стены успешно выровнены и склеены!\n• Выровнено по осям (0°/90°): ${alignedCount}\n• Склеено стыков: ${gluedCount}\n• Объединено прямых: ${mergedCount}`)
  }
}

// Convert Closed Perimeter of Walls to a Room
function createRoomFromClosedWalls() {
  alignAndMergeWalls(false)
  const walls = layoutData.value.walls || []
  if (walls.length < 3) {
    alert('Для сборки зоны нужно как минимум 3 стены.')
    return
  }

  const key = (x, y) => `${x},${y}`
  const parseKey = k => k.split(',').map(Number)
  const adj = new Map()

  function addEdge(uKey, vKey) {
    if (!adj.has(uKey)) adj.set(uKey, [])
    if (!adj.has(vKey)) adj.set(vKey, [])
    if (!adj.get(uKey).includes(vKey)) adj.get(uKey).push(vKey)
    if (!adj.get(vKey).includes(uKey)) adj.get(vKey).push(uKey)
  }

  walls.forEach(w => {
    const k1 = key(w.x1, w.y1)
    const k2 = key(w.x2, w.y2)
    if (k1 !== k2) addEdge(k1, k2)
  })

  const cycles = []
  function findCyclesDfs(curr, start, path) {
    for (const next of (adj.get(curr) || [])) {
      if (next === start && path.length >= 3) {
        cycles.push([...path])
        continue
      }
      if (!path.includes(next) && path.length < 24) {
        findCyclesDfs(next, start, [...path, next])
      }
    }
  }

  for (const startNode of adj.keys()) {
    if ((adj.get(startNode) || []).length >= 2) {
      findCyclesDfs(startNode, startNode, [startNode])
    }
  }

  if (cycles.length === 0) {
    alert('Не найден замкнутый контур стен.\n\nУбедитесь, что стены образуют замкнутый периметр без разрывов.')
    return
  }

  const validPolygons = []
  const seenPolys = new Set()

  for (const c of cycles) {
    const coords = c.map(parseKey)
    let area = 0
    for (let i = 0; i < coords.length; i++) {
      const j = (i + 1) % coords.length
      area += coords[i][0] * coords[j][1] - coords[j][0] * coords[i][1]
    }
    area = area / 2

    if (Math.abs(area) >= 150) {
      const sortedKeys = [...c].sort().join(';')
      if (!seenPolys.has(sortedKeys)) {
        seenPolys.add(sortedKeys)
        validPolygons.push({ points: coords, area: Math.abs(area) })
      }
    }
  }

  if (validPolygons.length === 0) {
    alert('Замкнутый контур стен слишком мал или вырожден.')
    return
  }

  validPolygons.sort((a, b) => a.area - b.area)
  const selectedPoly = validPolygons[0]

  addRoomModal.value = {
    points: selectedPoly.points,
    title: 'Комната из стен ' + ((layoutData.value.rooms?.length || 0) + 1),
    color: '#3b82f6',
  }
}

function confirmAddCircle() {
  if (!addCircleModal.value) return
  const { lat, lng, radius, title } = addCircleModal.value
  const newCircle = {
    id: 'o_' + Date.now(),
    type: 'circle',
    title: title || 'Колонна',
    x: Math.round(lng),
    y: Math.round(lat),
    radius: Math.max(5, Number(radius) || 30),
  }
  layoutData.value.obstacles = [...(layoutData.value.obstacles || []), newCircle]
  addCircleModal.value = null
  saveLayoutData()
}

// Delete Selected Element
async function deleteSelectedElement() {
  if (!selectedElement.value) return
  const { type, item } = selectedElement.value

  if (type === 'poi') {
    try {
      await poisApi.delete(item.id)
      pois.value = pois.value.filter(p => p.id !== item.id)
      isGraphDirty.value = true
    } catch (err) {
      console.error('Ошибка удаления POI:', err)
    }
  } else if (type === 'wall') {
    layoutData.value.walls = (layoutData.value.walls || []).filter(w => w.id !== item.id)
    await saveLayoutData(false)
  } else if (type === 'room') {
    layoutData.value.rooms = (layoutData.value.rooms || []).filter(r => r.id !== item.id)
    await saveLayoutData(false)
  } else if (type === 'obstacle') {
    layoutData.value.obstacles = (layoutData.value.obstacles || []).filter(o => o.id !== item.id)
    await saveLayoutData(false)
  } else if (type === 'corridor') {
    layoutData.value.corridors = (layoutData.value.corridors || []).filter(c => c.id !== item.id)
    await saveLayoutData(false)
  }

  selectedElement.value = null
  refreshMapLayers()
}

// Duplicate / Copy Selected Element
async function duplicateSelectedElement() {
  if (!selectedElement.value) return
  const { type, item } = selectedElement.value
  const offset = 40

  if (type === 'room') {
    const copy = {
      ...item,
      id: 'r_' + Date.now(),
      x: item.x + offset,
      y: item.y + offset,
      title: item.title ? `${item.title} (копия)` : 'Зона',
    }
    if (Array.isArray(item.points)) {
      copy.points = item.points.map(pt => [pt[0] + offset, pt[1] + offset])
    }
    layoutData.value.rooms = [...(layoutData.value.rooms || []), copy]
    selectedElement.value = { type: 'room', item: copy }
    await saveLayoutData()
  } else if (type === 'wall') {
    const copy = {
      ...item,
      id: 'w_' + Date.now(),
      x1: item.x1 + offset,
      y1: item.y1 + offset,
      x2: item.x2 + offset,
      y2: item.y2 + offset,
    }
    layoutData.value.walls = [...(layoutData.value.walls || []), copy]
    selectedElement.value = { type: 'wall', item: copy }
    await saveLayoutData()
  } else if (type === 'obstacle') {
    const copy = {
      ...item,
      id: 'o_' + Date.now(),
      x: item.x + offset,
      y: item.y + offset,
      title: item.title ? `${item.title} (копия)` : (item.type === 'circle' ? 'Колонна (копия)' : 'Препятствие (копия)'),
    }
    layoutData.value.obstacles = [...(layoutData.value.obstacles || []), copy]
    selectedElement.value = { type: 'obstacle', item: copy }
    await saveLayoutData()
  } else if (type === 'corridor') {
    const copy = {
      ...item,
      id: 'c_' + Date.now(),
      x1: item.x1 + offset,
      y1: item.y1 + offset,
      x2: item.x2 + offset,
      y2: item.y2 + offset,
    }
    layoutData.value.corridors = [...(layoutData.value.corridors || []), copy]
    selectedElement.value = { type: 'corridor', item: copy }
    await saveLayoutData()
  } else if (type === 'poi') {
    try {
      const { data: newPoi } = await poisApi.create(currentFloor.value.id, {
        title: (item.title || 'Точка') + ' (копия)',
        category: item.category || 'stand',
        description: item.description || '',
        x_coord: Number(item.x_coord ?? item.x) + offset,
        y_coord: Number(item.y_coord ?? item.y) + offset,
      })
      await loadFloorData()
      if (newPoi) {
        selectedElement.value = { type: 'poi', item: newPoi }
      }
      await triggerAutoGraph(false)
    } catch (err) {
      console.error('Ошибка дублирования POI:', err)
    }
  }

  refreshMapLayers()
}

// Clear All Layout Elements
async function handleClearLayout() {
  if (!confirm('Вы уверены, что хотите удалить все стены, зоны, препятствия и коридоры на этом этаже?')) {
    return
  }
  layoutData.value = { rooms: [], walls: [], obstacles: [], corridors: [] }
  selectedElement.value = null
  await saveLayoutData()
}

// Calibration
function startCalibration() {
  mode.value = 'view'
  cancelDrawing()
  selectedElement.value = null
  calibrating.value = true
  calibPoints = []
  calibResult.value = null
  if (calibLayer) calibLayer.clearLayers()
}

function handleCalibClick(lat, lng) {
  if (!window.L || !calibLayer) return
  calibPoints.push({ lat, lng })
  const dot = window.L.circleMarker([lat, lng], {
    radius: 6,
    color: '#ffffff',
    weight: 2,
    fillColor: '#f59e0b',
    fillOpacity: 1,
  })
  calibLayer.addLayer(dot)

  if (calibPoints.length === 2) {
    const dx = calibPoints[1].lng - calibPoints[0].lng
    const dy = calibPoints[1].lat - calibPoints[0].lat
    const pixels = Math.sqrt(dx * dx + dy * dy)
    calibResult.value = { pixels }
    window.L.polyline(
      [[calibPoints[0].lat, calibPoints[0].lng], [calibPoints[1].lat, calibPoints[1].lng]],
      { color: '#f59e0b', weight: 3, dashArray: '6, 6' }
    ).addTo(calibLayer)
    calibrating.value = false
    if (!calibDistance.value) {
      calibDistance.value = '1.0'
    }
  }
}

async function saveCalibration() {
  if (!calibResult.value || !calibDistance.value || !currentFloor.value) return
  const dist = parseFloat(calibDistance.value)
  if (isNaN(dist) || dist <= 0) {
    alert('Пожалуйста, укажите положительное реальное расстояние в метрах')
    return
  }
  const ppm = calibResult.value.pixels / dist
  try {
    await floorsApi.update(currentFloor.value.id, { ppm })
    currentFloor.value.ppm = ppm
    currentFloor.value.pixels_per_meter = ppm
    calibResult.value = null
    calibDistance.value = ''
    calibLayer?.clearLayers()
    alert(`Масштаб успешно сохранён: ${ppm.toFixed(2)} px/м`)
    await loadFloorData()
  } catch (e) {
    console.error('Ошибка сохранения масштаба:', e)
    alert('Ошибка при сохранении масштаба')
  }
}

// Adjust corridor width or circle radius for selected elements
function changeCorridorWidth(delta) {
  if (selectedElement.value?.type !== 'corridor') return
  const item = selectedElement.value.item
  const cur = item.width || 35
  item.width = Math.max(10, Math.min(200, cur + delta))
  drawCorridors()
  drawSelectionHandles()
  saveLayoutData(false)
}

function changeCircleRadius(delta) {
  if (selectedElement.value?.type !== 'obstacle' || selectedElement.value.item.type !== 'circle') return
  const item = selectedElement.value.item
  const cur = item.radius || 30
  item.radius = Math.max(10, Math.min(250, cur + delta))
  drawObstacles()
  drawSelectionHandles()
  saveLayoutData(false)
}

// Event handlers
async function onPoiAdded() {
  addPoiModal.value = null
  await loadFloorData()
  isGraphDirty.value = true
}

async function onPanoramaAdded() {
  addPanoramaModal.value = null
  await loadFloorData()
  isGraphDirty.value = true
  await triggerAutoGraph(false)
}

async function onFloorSelected(floor) {
  if (floor.id === currentFloor.value?.id) return
  currentFloor.value = floor
  router.replace(`/admin/spaces/${props.spaceId}/floors/${floor.id}/editor`)
  await nextTick()
  await initMap()
  await loadFloorData()
}

async function onPlanUploaded(uploadedFloor) {
  showUpload.value = false
  if (uploadedFloor) {
    currentFloor.value = uploadedFloor
    floors.value = floors.value.map(f => f.id === uploadedFloor.id ? uploadedFloor : f)
  } else {
    const { data: spaceData } = await spacesApi.get(props.spaceId)
    floors.value = spaceData?.floors || []
    currentFloor.value = floors.value.find(f => String(f.id) === String(props.floorId)) || floors.value[0]
  }
  await nextTick()
  await initMap()
  await loadFloorData()
}

async function onFloorCreated(floor) {
  floors.value.push(floor)
  await onFloorSelected(floor)
}

function updateBlueprintOpacity(val) {
  blueprintOpacity.value = val
  if (overlayLayer) {
    overlayLayer.setOpacity(val)
  }
}

async function handleRotatePlan(delta) {
  if (!currentFloor.value) return
  const nextRot = (((blueprintRotation.value + delta) % 360) + 360) % 360
  blueprintRotation.value = nextRot
  if (!layoutData.value) {
    layoutData.value = { rooms: [], walls: [], obstacles: [], corridors: [] }
  }
  layoutData.value.blueprint_rotation = nextRot
  if (currentFloor.value.layout_data) {
    currentFloor.value.layout_data.blueprint_rotation = nextRot
  }

  const rawPlanUrl = resolveMediaUrl(currentFloor.value.plan_url || currentFloor.value.plan_image_url)
  if (overlayLayer && rawPlanUrl && window.L) {
    const isSwapped = nextRot === 90 || nextRot === 270
    const origW = currentFloor.value.width_px || currentFloor.value.width || 1400
    const origH = currentFloor.value.height_px || currentFloor.value.height || 900
    const w = isSwapped ? origH : origW
    const h = isSwapped ? origW : origH
    const bounds = [[0, 0], [h, w]]
    const displayUrl = await getRotatedPlanUrl(rawPlanUrl, nextRot)
    overlayLayer.setUrl(displayUrl)
    overlayLayer.setBounds(bounds)
    map?.fitBounds(bounds)
  }
  await saveLayoutData(false)
}

function toggleShowGraph(val) {
  showGraph.value = val
  drawNavGraph()
}

function nudgeSelected(dx, dy) {
  if (!selectedElement.value) return
  const { type, item } = selectedElement.value
  if (type === 'room') {
    item.x = Math.round(item.x + dx)
    item.y = Math.round(item.y + dy)
    if (Array.isArray(item.points)) {
      item.points = item.points.map(pt => [Math.round(pt[0] + dx), Math.round(pt[1] + dy)])
    }
    saveLayoutData(false)
  } else if (type === 'obstacle' && item.type === 'rect') {
    item.x = Math.round(item.x + dx)
    item.y = Math.round(item.y + dy)
    saveLayoutData(false)
  } else if (type === 'obstacle' && item.type === 'circle') {
    item.x = Math.round(item.x + dx)
    item.y = Math.round(item.y + dy)
    saveLayoutData(false)
  } else if (type === 'wall' || type === 'corridor') {
    item.x1 = Math.round(item.x1 + dx)
    item.y1 = Math.round(item.y1 + dy)
    item.x2 = Math.round(item.x2 + dx)
    item.y2 = Math.round(item.y2 + dy)
    saveLayoutData(false)
  } else if (type === 'poi') {
    const px = Math.round(Number(item.x_coord ?? item.x ?? 0) + dx)
    const py = Math.round(Number(item.y_coord ?? item.y ?? 0) + dy)
    item.x_coord = px
    item.y_coord = py
    item.x = px
    item.y = py
    poisApi.update(item.id, { x_coord: px, y_coord: py }).then(() => {
      isGraphDirty.value = true
      refreshMapLayers()
    })
  }
}

async function onDeletePlan() {
  if (!currentFloor.value) return
  if (!confirm('Вы уверены, что хотите удалить чертёж-подложку этого этажа?')) return

  try {
    const { data: updatedFloor } = await floorsApi.deletePlan(currentFloor.value.id)
    if (updatedFloor) {
      currentFloor.value.plan_url = null
      currentFloor.value.plan_image_url = null
      currentFloor.value.plan_original_key = null
      currentFloor.value.plan_optimized_key = null
      if (overlayLayer && map) {
        map.removeLayer(overlayLayer)
        overlayLayer = null
      }
      floors.value = floors.value.map(f => f.id === updatedFloor.id ? { ...f, plan_url: null, plan_image_url: null } : f)
    }
  } catch (err) {
    console.error('Ошибка удаления чертежа:', err)
    alert('Не удалось удалить чертёж этажа')
  }
}

function handleKeyDown(e) {
  if ((e.ctrlKey || e.metaKey) && (e.key === 'd' || e.key === 'D' || e.key === 'c' || e.key === 'C')) {
    if (selectedElement.value && mode.value === 'view') {
      e.preventDefault()
      duplicateSelectedElement()
    }
  } else if (e.key === 'Delete' || e.key === 'Backspace') {
    const tag = document.activeElement?.tagName?.toLowerCase()
    if (tag !== 'input' && tag !== 'textarea') {
      if (mode.value === 'poly-room') {
        e.preventDefault()
        removeLastPolyPoint()
      } else if (selectedElement.value && mode.value === 'view') {
        e.preventDefault()
        deleteSelectedElement()
      }
    }
  } else if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
    const tag = document.activeElement?.tagName?.toLowerCase()
    if (tag !== 'input' && tag !== 'textarea') {
      if (selectedElement.value && mode.value === 'view') {
        e.preventDefault()
        const step = e.shiftKey ? 40 : 10
        if (e.key === 'ArrowLeft') nudgeSelected(-step, 0)
        if (e.key === 'ArrowRight') nudgeSelected(step, 0)
        if (e.key === 'ArrowUp') nudgeSelected(0, step)
        if (e.key === 'ArrowDown') nudgeSelected(0, -step)
      }
    }
  } else if (e.key === 'Enter') {
    if (mode.value === 'poly-room' && polyPoints.value.length >= 3) {
      e.preventDefault()
      finishPolyRoom()
    }
  } else if (e.key === 'Escape') {
    if (mode.value === 'poly-room') {
      cancelPolyRoom()
      mode.value = 'view'
    } else if (drawingPoint.value) {
      cancelDrawing()
    } else if (selectedElement.value) {
      selectedElement.value = null
      refreshMapLayers()
    }
  }
}

onMounted(async () => {
  window.addEventListener('keydown', handleKeyDown)
  await fetchData()
  await nextTick()
  await initMap()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  if (map) map.remove()
})
</script>

<template>
  <div class="relative flex h-full overflow-hidden" style="height: calc(100vh - 56px)">
    <!-- Mobile Sidebar Backdrop Overlay -->
    <div
      v-if="isMobileSidebarOpen"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 lg:hidden"
      @click="isMobileSidebarOpen = false"
    ></div>

    <!-- Sidebar: regular panel on desktop (lg+), sliding drawer on mobile/tablet -->
    <div
      class="fixed inset-y-0 left-0 z-40 lg:static lg:z-auto transition-transform duration-300 ease-in-out"
      :class="isMobileSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'"
    >
      <FloorSidebar
        :space="space"
        :floors="floors"
        :currentFloor="currentFloor"
        :mode="mode"
        :calibrating="calibrating"
        :calibResult="calibResult"
        :blueprintOpacity="blueprintOpacity"
        :blueprintRotation="blueprintRotation"
        :showGraph="showGraph"
        :graphStats="graphStats"
        :generatingGraph="generatingGraph"
        :layoutCounts="layoutCounts"
        :corridorWidth="corridorWidth"
        :is-graph-dirty="isGraphDirty"
        @update:corridorWidth="corridorWidth = $event"
        v-model:calibDistance="calibDistance"
        @select-floor="onFloorSelected"
        @floor-created="onFloorCreated"
        @upload-plan="showUpload = true; isMobileSidebarOpen = false"
        @set-mode="mode = $event; cancelDrawing(); cancelPolyRoom(); selectedElement = null; isMobileSidebarOpen = false"
        @auto-graph="handleBuildGraph"
        @toggle-show-graph="toggleShowGraph"
        @update:blueprintOpacity="updateBlueprintOpacity"
        @rotate-plan="handleRotatePlan"
        @clear-layout="handleClearLayout"
        @align-walls="alignAndMergeWalls(true)"
        @walls-to-room="createRoomFromClosedWalls()"
        @start-calib="startCalibration(); isMobileSidebarOpen = false"
        @save-calib="saveCalibration"
        @cancel-calib="calibrating = false; calibPoints = []; calibLayer?.clearLayers(); calibResult = null"
        @delete-plan="onDeletePlan"
        @close-mobile="isMobileSidebarOpen = false"
      />
    </div>

    <!-- Map Area -->
    <div class="flex-1 relative overflow-hidden architectural-canvas" style="background: #070c18">
      <!-- Floating Top Bar Action: Save & Build Navigation Graph -->
      <div class="absolute top-4 right-4 z-20 flex items-center gap-2 pointer-events-auto">
        <button
          v-if="isGraphDirty"
          @click="handleBuildGraph"
          :disabled="generatingGraph || savingLayout"
          class="px-3.5 py-2 rounded-xl text-xs font-bold flex items-center gap-2 shadow-xl backdrop-blur-md transition-all cursor-pointer active:scale-95 bg-amber-500 hover:bg-amber-400 text-slate-950 border border-amber-300 ring-2 ring-amber-400/40 animate-pulse"
          title="Планировка изменилась! Нажмите для пересчёта навигационного графа."
        >
          <span v-if="generatingGraph" class="spinner w-3.5 h-3.5 border-slate-950"></span>
          <Zap v-else :size="14" />
          <span>{{ generatingGraph ? 'Расчёт путей...' : '⚡ Сохранить и построить граф' }}</span>
        </button>
        <button
          v-else
          @click="handleBuildGraph"
          :disabled="generatingGraph || savingLayout"
          class="px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 shadow-md backdrop-blur-md transition-all cursor-pointer active:scale-95 bg-slate-900/85 hover:bg-slate-800 text-slate-200 border border-slate-700/80"
          title="Навигационный граф актуален. Нажмите для принудительного пересчёта."
        >
          <span v-if="generatingGraph" class="spinner w-3 h-3 text-blue-400"></span>
          <Zap v-else :size="13" class="text-blue-400" />
          <span>{{ generatingGraph ? 'Расчёт...' : 'Обновить граф' }}</span>
        </button>
      </div>

      <!-- Mobile Floating Sidebar Toggle Button -->
      <button
        type="button"
        @click="isMobileSidebarOpen = !isMobileSidebarOpen"
        class="lg:hidden absolute bottom-5 left-4 z-20 px-3.5 py-2.5 rounded-2xl bg-slate-900/95 hover:bg-slate-800 text-white border border-slate-700/80 shadow-2xl backdrop-blur-md flex items-center gap-2 text-xs font-semibold cursor-pointer active:scale-95"
      >
        <Layers class="w-4 h-4 text-blue-400" />
        <span>Инструменты</span>
        <span v-if="mode !== 'view'" class="w-2 h-2 rounded-full bg-blue-500"></span>
      </button>

      <!-- Loading overlay -->
      <div v-if="loading" class="absolute inset-0 flex items-center justify-center z-20">
        <div class="flex flex-col items-center gap-3">
          <span class="spinner" style="width:32px;height:32px;border-width:3px;color:var(--accent)"></span>
          <p class="text-sm" style="color: var(--text-muted)">Загрузка планировки...</p>
        </div>
      </div>

      <!-- Leaflet map container -->
      <div id="floor-map" class="w-full h-full" style="z-index: 1"></div>

      <!-- Top Mode Instruction Floating Banner -->
      <div v-if="mode !== 'view'" class="absolute top-4 left-1/2 -translate-x-1/2 z-10 card-glass px-3 sm:px-4 py-2 flex items-center gap-2 sm:gap-3 text-xs sm:text-sm font-medium shadow-xl border border-slate-700/60 backdrop-blur-md max-w-[92vw] text-center">
        <span v-if="drawingPoint || polyPoints.length > 0" class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping shrink-0"></span>
        <span v-else class="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse shrink-0"></span>

        <span v-if="mode === 'room' && !drawingPoint" class="text-slate-100 truncate">Кликните первый угол зоны</span>
        <span v-if="mode === 'room' && drawingPoint" class="text-amber-300 truncate">Кликните второй угол для завершения зоны</span>

        <template v-if="mode === 'poly-room'">
          <span v-if="polyPoints.length === 0" class="text-slate-100 truncate">Кликайте точки контура зоны (L-образные и любые другие формы)</span>
          <span v-else class="text-indigo-300 font-mono">Вершин: {{ polyPoints.length }}</span>

          <button
            v-if="polyPoints.length >= 3"
            type="button"
            @click="finishPolyRoom"
            class="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs shadow transition-all cursor-pointer flex items-center gap-1 active:scale-95"
            title="Замкнуть и создать многоугольную зону"
          >
            <Check :size="13" /> Завершить зону
          </button>
          <button
            v-if="polyPoints.length > 0"
            type="button"
            @click="removeLastPolyPoint"
            class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition-all cursor-pointer"
            title="Отменить последнюю точку (Backspace)"
          >
            ⌫
          </button>
        </template>

        <span v-if="mode === 'wall' && !drawingPoint" class="text-slate-100 truncate">Кликните начало стены (примагничивание к углам)</span>
        <span v-if="mode === 'wall' && drawingPoint" class="text-amber-300 truncate">Кликните конец стены (авто-выравнивание 90°)</span>

        <span v-if="mode === 'circle'" class="text-slate-100 truncate">Кликните для установки колонны</span>

        <span v-if="mode === 'rect' && !drawingPoint" class="text-slate-100 truncate">Кликните первый угол препятствия</span>
        <span v-if="mode === 'rect' && drawingPoint" class="text-amber-300 truncate">Кликните второй угол препятствия</span>

        <span v-if="mode === 'corridor' && !drawingPoint" class="text-slate-100 truncate">Кликните начало коридора</span>
        <span v-if="mode === 'corridor' && drawingPoint" class="text-amber-300 truncate">Кликните конец коридора</span>

        <span v-if="mode === 'poi'" class="text-slate-100 truncate">Кликните для установки POI</span>
        <span v-if="mode === 'panorama'" class="text-purple-300 truncate">Кликните для установки 360° панорамы</span>

        <button @click="mode = 'view'; cancelDrawing()" class="btn btn-ghost px-2 py-0.5 text-xs text-slate-400 hover:text-white shrink-0 ml-1">
          ✕
        </button>
      </div>

      <!-- Selected Element Floating Toolbar -->
      <div v-if="selectedElement && mode === 'view'" class="absolute bottom-16 sm:bottom-6 left-1/2 -translate-x-1/2 z-10 card-glass px-3 sm:px-4 py-2 sm:py-2.5 flex flex-wrap sm:flex-nowrap items-center justify-center gap-2 sm:gap-4 text-xs font-medium shadow-2xl border border-slate-700 backdrop-blur-md rounded-xl max-w-[95vw]">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-blue-400 shrink-0"></span>
          <span class="text-slate-300 hidden sm:inline">Выбран элемент:</span>
          <b class="text-white capitalize truncate max-w-[140px] sm:max-w-none">
            {{ selectedElement.type === 'room' ? `Зона "${selectedElement.item.title || 'Без названия'}"` : '' }}
            {{ selectedElement.type === 'wall' ? 'Стена' : '' }}
            {{ selectedElement.type === 'obstacle' ? `Препятствие "${selectedElement.item.title || selectedElement.item.type}"` : '' }}
            {{ selectedElement.type === 'corridor' ? 'Коридор' : '' }}
            {{ selectedElement.type === 'poi' ? `Точка "${selectedElement.item.title}"` : '' }}
          </b>
          <span
            v-if="selectedElement.type === 'poi' && selectedElement.item.panorama_id"
            class="bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[10px] px-2 py-0.5 rounded-full flex items-center gap-1 font-semibold"
          >
            <Camera :size="10" /> 360° Панорама
          </span>
        </div>

        <!-- Corridor Width Control -->
        <div v-if="selectedElement.type === 'corridor'" class="flex items-center gap-1.5 bg-slate-800/90 px-2 py-1 rounded-lg border border-emerald-500/30">
          <span class="text-[11px] text-emerald-300 font-medium">Ширина:</span>
          <button @click="changeCorridorWidth(-5)" class="w-5 h-5 flex items-center justify-center rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Уменьшить ширину">-</button>
          <span class="font-mono text-emerald-400 font-bold px-1">{{ selectedElement.item.width || 35 }} px</span>
          <button @click="changeCorridorWidth(5)" class="w-5 h-5 flex items-center justify-center rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Увеличить ширину">+</button>
        </div>

        <!-- Column Radius Control -->
        <div v-if="selectedElement.type === 'obstacle' && selectedElement.item.type === 'circle'" class="flex items-center gap-1.5 bg-slate-800/90 px-2 py-1 rounded-lg border border-cyan-500/30">
          <span class="text-[11px] text-cyan-300 font-medium">Радиус:</span>
          <button @click="changeCircleRadius(-5)" class="w-5 h-5 flex items-center justify-center rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Уменьшить радиус">-</button>
          <span class="font-mono text-cyan-400 font-bold px-1">{{ selectedElement.item.radius || 30 }} px</span>
          <button @click="changeCircleRadius(5)" class="w-5 h-5 flex items-center justify-center rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Увеличить радиус">+</button>
        </div>

        <!-- Nudge / Move Controls -->
        <div class="flex items-center gap-1 bg-slate-800/80 px-2 py-1 rounded-lg border border-slate-700/80">
          <span class="text-[10px] text-slate-400 mr-1 select-none font-mono hidden sm:inline">Сдвиг:</span>
          <button @click="nudgeSelected(-10, 0)" class="px-1.5 py-0.5 rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Сдвиг влево (←)">←</button>
          <button @click="nudgeSelected(0, 10)" class="px-1.5 py-0.5 rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Сдвиг вверх (↑)">↑</button>
          <button @click="nudgeSelected(0, -10)" class="px-1.5 py-0.5 rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Сдвиг вниз (↓)">↓</button>
          <button @click="nudgeSelected(10, 0)" class="px-1.5 py-0.5 rounded hover:bg-slate-700 text-slate-300 hover:text-white" title="Сдвиг вправо (→)">→</button>
        </div>
        <div class="flex items-center gap-1.5 sm:gap-2">
          <button @click="duplicateSelectedElement" class="btn btn-ghost text-blue-400 hover:text-blue-300 hover:bg-blue-500/10 px-2 py-1 gap-1" title="Дублировать (Ctrl+D)">
            <Copy :size="13" /> <span class="hidden sm:inline">Копировать</span>
          </button>
          <button @click="deleteSelectedElement" class="btn btn-ghost text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 px-2 py-1 gap-1" title="Удалить (Delete)">
            <Trash2 :size="13" /> <span class="hidden sm:inline">Удалить</span>
          </button>
          <button @click="selectedElement = null; refreshMapLayers()" class="btn btn-ghost text-slate-400 px-2 py-1">
            ✕
          </button>
        </div>
      </div>

      <!-- Calibration Active Banner -->
      <div v-if="calibrating" class="absolute top-4 left-1/2 -translate-x-1/2 z-20 card-glass px-4 py-2.5 rounded-xl text-sm font-semibold text-amber-300 border border-amber-500/40 shadow-2xl backdrop-blur-md flex items-center gap-2">
        <span class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping"></span>
        <span>🎯 {{ calibPoints.length === 0 ? 'Кликните первую точку на плане' : 'Кликните вторую точку на плане' }}</span>
        <button @click="calibrating = false; calibPoints = []; calibLayer?.clearLayers(); calibResult = null" class="ml-2 text-xs text-slate-400 hover:text-white underline cursor-pointer">Отмена</button>
      </div>

      <!-- Floating Calibration Result Dialog on Map -->
      <div v-if="calibResult && !calibrating" class="absolute top-4 left-1/2 -translate-x-1/2 z-20 card-glass p-4 rounded-xl shadow-2xl border border-amber-500/50 backdrop-blur-md w-80 text-xs space-y-2.5">
        <div class="flex items-center justify-between">
          <b class="text-amber-300 text-sm font-semibold flex items-center gap-1.5">
            <Ruler :size="15" /> Задать масштаб
          </b>
          <button @click="calibResult = null; calibLayer?.clearLayers()" class="text-slate-400 hover:text-white cursor-pointer">✕</button>
        </div>
        <p class="text-slate-300">Расстояние на плане: <b class="text-white font-mono">{{ calibResult.pixels.toFixed(1) }} px</b></p>
        <div>
          <label class="block text-slate-400 mb-1">Реальное расстояние в метрах:</label>
          <input
            type="number"
            step="0.1"
            min="0.01"
            v-model="calibDistance"
            class="input text-xs py-1.5 w-full font-mono text-emerald-400"
            placeholder="например 1.0 или 5.5"
            autofocus
          />
        </div>
        <div class="flex gap-2 pt-1">
          <button @click="saveCalibration" class="btn btn-primary flex-1 justify-center text-xs py-1.5">
            <Check :size="14" /> Сохранить
          </button>
          <button @click="calibResult = null; calibLayer?.clearLayers()" class="btn btn-ghost text-xs py-1.5">
            Отмена
          </button>
        </div>
      </div>

      <!-- Syncing Indicator -->
      <div v-if="savingLayout" class="absolute bottom-4 right-4 z-10 card-glass px-3 py-1.5 rounded-lg text-xs flex items-center gap-2 text-blue-400 bg-slate-900/90 border border-blue-500/30">
        <span class="spinner w-3 h-3"></span>
        <span>Сохранение планировки...</span>
      </div>
    </div>

    <!-- Upload Blueprint Panel -->
    <PlanUploadPanel
      v-if="showUpload && currentFloor"
      :floorId="currentFloor.id"
      @close="showUpload = false"
      @uploaded="onPlanUploaded"
    />

    <!-- Add POI Modal -->
    <AddPoiModal
      v-if="addPoiModal && currentFloor"
      :floorId="currentFloor.id"
      :coords="addPoiModal"
      @close="addPoiModal = null"
      @created="onPoiAdded"
    />

    <!-- Add 360 Panorama Modal -->
    <AddPanoramaModal
      v-if="addPanoramaModal && currentFloor"
      :floor-id="currentFloor.id"
      :coords="addPanoramaModal"
      @close="addPanoramaModal = null"
      @created="onPanoramaAdded"
    />

    <!-- Add Room Modal -->
    <div v-if="addRoomModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div class="card w-full max-w-sm p-5 space-y-4 shadow-2xl border border-slate-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <component :is="addRoomModal.points ? Shapes : Square" :size="18" :class="addRoomModal.points ? 'text-indigo-400' : 'text-blue-400'" />
            <h3 class="font-semibold text-white text-sm">
              {{ addRoomModal.points ? `Зона-многоугольник (${addRoomModal.points.length} вершин)` : 'Новая зона / комната' }}
            </h3>
          </div>
          <button @click="addRoomModal = null" class="btn btn-ghost p-1"><X :size="16" /></button>
        </div>

        <div>
          <label class="label text-xs">Название зоны</label>
          <input v-model="addRoomModal.title" type="text" class="input text-xs py-2" placeholder="Зал пленарных заседаний / Зона отдыха" autofocus />
        </div>

        <div>
          <label class="label text-xs">Цветовая тема</label>
          <div class="flex gap-2">
            <button
              v-for="color in ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#f43f5e', '#64748b']"
              :key="color"
              type="button"
              @click="addRoomModal.color = color"
              class="w-7 h-7 rounded-full border-2 transition-transform"
              :style="`background: ${color}; border-color: ${addRoomModal.color === color ? '#ffffff' : 'transparent'}; transform: ${addRoomModal.color === color ? 'scale(1.2)' : 'scale(1)'}`"
            ></button>
          </div>
        </div>

        <div class="flex gap-2 pt-2">
          <button @click="addRoomModal = null" class="btn btn-ghost flex-1 justify-center text-xs py-1.5">Отмена</button>
          <button @click="confirmAddRoom" class="btn btn-primary flex-1 justify-center text-xs py-1.5">
            <Check :size="14" /> Добавить зону
          </button>
        </div>
      </div>
    </div>

    <!-- Add Circle Modal -->
    <div v-if="addCircleModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div class="card w-full max-w-sm p-5 space-y-4 shadow-2xl border border-slate-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Circle :size="18" class="text-cyan-400" />
            <h3 class="font-semibold text-white text-sm">Параметры колонны / объекта</h3>
          </div>
          <button @click="addCircleModal = null" class="btn btn-ghost p-1"><X :size="16" /></button>
        </div>

        <div>
          <label class="label text-xs">Название (необязательно)</label>
          <input v-model="addCircleModal.title" type="text" class="input text-xs py-2" placeholder="Колонна 1 / Круглый стенд" />
        </div>

        <div>
          <label class="label text-xs">Радиус (px)</label>
          <input v-model.number="addCircleModal.radius" type="number" min="5" max="300" class="input text-xs py-2" />
          <p class="text-[11px] text-slate-400 mt-1">Маршруты навигации будут огибать объект с отступом безопасности +30 px.</p>
        </div>

        <div class="flex gap-2 pt-2">
          <button @click="addCircleModal = null" class="btn btn-ghost flex-1 justify-center text-xs py-1.5">Отмена</button>
          <button @click="confirmAddCircle" class="btn btn-primary flex-1 justify-center text-xs py-1.5">
            <Check :size="14" /> Добавить
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
/* Architectural Canvas Grid */
.architectural-canvas {
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 50px 50px;
}

.leaflet-container {
  background: transparent !important;
}

/* POI Marker in Editor */
.poi-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  user-select: none;
  filter: drop-shadow(0 2px 5px rgba(0,0,0,0.7));
  transition: transform 0.15s ease;
}
.poi-marker:hover {
  transform: scale(1.1);
}
.poi-marker.selected .poi-icon-box {
  box-shadow: 0 0 0 3px #ffffff, 0 0 15px rgba(59,130,246,0.8);
  transform: scale(1.15);
}
.poi-icon-box {
  width: 28px;
  height: 28px;
  border-radius: 9999px;
  background: #1e293b;
  border: 2px solid #3b82f6;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}
.poi-name-tag {
  font-size: 10px;
  background: rgba(15,23,42,0.95);
  color: #f1f5f9;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  border: 1px solid rgba(51,65,85,0.6);
}

/* Room & Obstacle Badges */
.room-label-badge,
.obstacle-label-badge {
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
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.85);
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid rgba(71, 85, 105, 0.4);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
  white-space: nowrap;
  pointer-events: none;
  user-select: none;
}
.room-title-tag.selected {
  color: #ffffff;
  border-color: #60a5fa;
  background: rgba(30, 58, 138, 0.9);
}

.obstacle-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: max-content;
  max-width: none;
  font-size: 9px;
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.8);
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  pointer-events: none;
}

/* Перемещение элементов мышью */
.element-draggable,
.leaflet-interactive.element-draggable {
  cursor: grab !important;
}
.element-draggable:active,
.leaflet-interactive.element-draggable:active {
  cursor: grabbing !important;
}

.selection-handle-wrapper {
  background: transparent !important;
  border: none !important;
}
</style>
