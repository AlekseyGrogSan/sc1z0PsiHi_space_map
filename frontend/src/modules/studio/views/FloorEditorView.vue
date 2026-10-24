<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { floorsApi, poisApi, navApi, spacesApi } from '../../../api'
import FloorSidebar from '../components/FloorSidebar.vue'
import PlanUploadPanel from '../components/PlanUploadPanel.vue'
import AddPoiModal from '../components/AddPoiModal.vue'
import {
  ArrowLeft, Layers, Trash2, Check, X, Square, Minus, Circle, Box,
  Footprints, MapPin, Zap, Eye, RotateCcw, Copy
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
const mode = ref('view') // 'view' | 'room' | 'wall' | 'circle' | 'rect' | 'corridor' | 'poi'
const showUpload = ref(false)
const addPoiModal = ref(null) // { x, y } in pixel coords
const addRoomModal = ref(null) // { p1, p2, title, color }
const addCircleModal = ref(null) // { lat, lng, radius, title }
const selectedElement = ref(null) // { type, item }
const drawingPoint = ref(null) // { lat, lng } start point for 2-click drawing
const isMobileSidebarOpen = ref(false) // Mobile tools drawer state

// Blueprint & Graph options
const blueprintOpacity = ref(0.85)
const showGraph = ref(false)
const generatingGraph = ref(false)
const savingLayout = ref(false)
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
  }

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
  const planUrl = floor?.plan_url || floor?.plan_image_url
  const w = floor?.width_px || floor?.width || 1400
  const h = floor?.height_px || floor?.height || 900

  map = L.map('floor-map', {
    crs: L.CRS.Simple,
    minZoom: -3,
    maxZoom: 3,
    zoomSnap: 0.25,
    attributionControl: false,
  })

  const bounds = [[0, 0], [h, w]]

  if (planUrl) {
    overlayLayer = L.imageOverlay(planUrl, bounds, { opacity: blueprintOpacity.value }).addTo(map)
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
    if (mode.value !== 'view') return
    window.L.DomEvent.stopPropagation(e)
    if (justDragged) return
    if (onClick) onClick(e)
  })
}

// 1. Draw Rooms (Draggable)
function drawRooms() {
  if (!roomsLayer || !window.L) return
  roomsLayer.clearLayers()
  const L = window.L

  const rooms = layoutData.value.rooms || []
  rooms.forEach(r => {
    const isSel = selectedElement.value?.type === 'room' && selectedElement.value?.item?.id === r.id
    const p1 = [r.y, r.x]
    const p2 = [r.y + r.height, r.x + r.width]
    const rect = L.rectangle([p1, p2], {
      color: isSel ? '#ffffff' : (r.color || '#3b82f6'),
      weight: isSel ? 3 : 1.5,
      dashArray: isSel ? '4, 4' : null,
      fillColor: r.color || '#3b82f6',
      fillOpacity: isSel ? 0.35 : 0.2,
      className: 'element-draggable',
    })

    const origX = r.x
    const origY = r.y
    const origW = r.width
    const origH = r.height

    attachShapeDrag(rect, {
      onDrag: (dx, dy) => {
        rect.setBounds([[origY + dy, origX + dx], [origY + origH + dy, origX + origW + dx]])
      },
      onDragEnd: async (dx, dy) => {
        r.x = Math.round(origX + dx)
        r.y = Math.round(origY + dy)
        selectedElement.value = { type: 'room', item: r }
        await saveLayoutData(true)
      },
      onClick: () => {
        selectedElement.value = { type: 'room', item: r }
        refreshMapLayers()
      },
    })
    roomsLayer.addLayer(rect)

    if (r.title) {
      const center = [r.y + r.height / 2, r.x + r.width / 2]
      const label = L.divIcon({
        className: 'room-label-badge',
        html: `<div class="room-title-tag ${isSel ? 'selected' : ''}">${r.title}</div>`,
        iconAnchor: [50, 10],
      })
      roomsLayer.addLayer(L.marker(center, { icon: label, interactive: false }))
    }
  })
}

// 2. Draw Corridors (Draggable)
function drawCorridors() {
  if (!corridorsLayer || !window.L) return
  corridorsLayer.clearLayers()
  const L = window.L

  const corridors = layoutData.value.corridors || []
  corridors.forEach(c => {
    const isSel = selectedElement.value?.type === 'corridor' && selectedElement.value?.item?.id === c.id
    const poly = L.polyline(
      [[c.y1, c.x1], [c.y2, c.x2]],
      {
        color: isSel ? '#34d399' : 'rgba(59, 130, 246, 0.35)',
        weight: c.width || 24,
        lineCap: 'round',
        lineJoin: 'round',
        className: 'element-draggable',
      }
    )

    const origX1 = c.x1
    const origY1 = c.y1
    const origX2 = c.x2
    const origY2 = c.y2

    attachShapeDrag(poly, {
      onDrag: (dx, dy) => {
        poly.setLatLngs([[origY1 + dy, origX1 + dx], [origY2 + dy, origX2 + dx]])
      },
      onDragEnd: async (dx, dy) => {
        c.x1 = Math.round(origX1 + dx)
        c.y1 = Math.round(origY1 + dy)
        c.x2 = Math.round(origX2 + dx)
        c.y2 = Math.round(origY2 + dy)
        selectedElement.value = { type: 'corridor', item: c }
        await saveLayoutData(true)
      },
      onClick: () => {
        selectedElement.value = { type: 'corridor', item: c }
        refreshMapLayers()
      },
    })
    corridorsLayer.addLayer(poly)
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
          await saveLayoutData(true)
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
          iconAnchor: [35, 10],
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
          await saveLayoutData(true)
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
        await saveLayoutData(true)
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
    const emoji = CATEGORY_ICONS[poi.category] || '📍'
    const poiTitle = poi.title || poi.name || ''
    const icon = L.divIcon({
      className: '',
      html: `
        <div class="poi-marker ${isSel ? 'selected' : ''}" data-id="${poi.id}" title="${poiTitle}">
          <span class="poi-icon-box">${emoji}</span>
          <span class="poi-name-tag">${poiTitle}</span>
        </div>
      `,
      iconAnchor: [16, 16],
    })
    const py = Number(poi.y_coord ?? poi.y ?? 0)
    const px = Number(poi.x_coord ?? poi.x ?? 0)
    const marker = L.marker([py, px], { icon, draggable: true })

    marker.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      const npx = Math.round(lng)
      const npy = Math.round(lat)
      poi.y_coord = npy
      poi.x_coord = npx
      poi.x = npx
      poi.y = npy
      selectedElement.value = { type: 'poi', item: poi }
      await poisApi.update(poi.id, { y_coord: npy, x_coord: npx })
      await triggerAutoGraph(false)
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
      item.x1 = Math.round(lng)
      item.y1 = Math.round(lat)
      await saveLayoutData(true)
    })
    handlesLayer.addLayer(h1)

    const h2 = L.marker([item.y2, item.x2], { icon: createHandleIcon('#f43f5e'), draggable: true })
    h2.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      item.x2 = Math.round(lng)
      item.y2 = Math.round(lat)
      await saveLayoutData(true)
    })
    handlesLayer.addLayer(h2)
  } else if (type === 'corridor') {
    const h1 = L.marker([item.y1, item.x1], { icon: createHandleIcon('#10b981'), draggable: true })
    h1.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      item.x1 = Math.round(lng)
      item.y1 = Math.round(lat)
      await saveLayoutData(true)
    })
    handlesLayer.addLayer(h1)

    const h2 = L.marker([item.y2, item.x2], { icon: createHandleIcon('#10b981'), draggable: true })
    h2.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      item.x2 = Math.round(lng)
      item.y2 = Math.round(lat)
      await saveLayoutData(true)
    })
    handlesLayer.addLayer(h2)
  } else if (type === 'room') {
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
        await saveLayoutData(true)
      })
      handlesLayer.addLayer(h)
    })
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
        await saveLayoutData(true)
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
      await saveLayoutData(true)
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

// Save Layout to Backend and Auto-Trigger Backend Graph
async function saveLayoutData(triggerGraph = true) {
  if (!currentFloor.value) return
  savingLayout.value = true
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
      refreshMapLayers()
    }
  } catch (err) {
    console.error('Ошибка генерации навигационного графа:', err)
  } finally {
    if (showSpinner) generatingGraph.value = false
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
    addPoiModal.value = { x: lng, y: lat }
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

  if (mode.value === 'wall') {
    if (!drawingPoint.value) {
      drawingPoint.value = { lat, lng }
    } else {
      const p1 = drawingPoint.value
      const p2 = { lat, lng }
      const newWall = {
        id: 'w_' + Date.now(),
        x1: Math.round(p1.lng),
        y1: Math.round(p1.lat),
        x2: Math.round(p2.lng),
        y2: Math.round(p2.lat),
        thickness: 6,
      }
      layoutData.value.walls = [...(layoutData.value.walls || []), newWall]
      drawingPoint.value = null
      previewLayer?.clearLayers()
      saveLayoutData()
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
        width: 24,
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
  if (!previewLayer || !window.L || !drawingPoint.value) return
  previewLayer.clearLayers()
  const L = window.L
  const p1 = drawingPoint.value
  const p2 = e.latlng

  if (mode.value === 'wall') {
    L.polyline([[p1.lat, p1.lng], [p2.lat, p2.lng]], {
      color: '#cbd5e1',
      weight: 6,
      dashArray: '6, 6',
    }).addTo(previewLayer)
  } else if (mode.value === 'corridor') {
    L.polyline([[p1.lat, p1.lng], [p2.lat, p2.lng]], {
      color: 'rgba(59, 130, 246, 0.4)',
      weight: 24,
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
  previewLayer?.clearLayers()
}

// Modal Confirmations
function confirmAddRoom() {
  if (!addRoomModal.value) return
  const { p1, p2, title, color } = addRoomModal.value
  const minX = Math.round(Math.min(p1.lng, p2.lng))
  const maxX = Math.round(Math.max(p1.lng, p2.lng))
  const minY = Math.round(Math.min(p1.lat, p2.lat))
  const maxY = Math.round(Math.max(p1.lat, p2.lat))

  const newRoom = {
    id: 'r_' + Date.now(),
    title: title || 'Зона',
    color: color || '#3b82f6',
    x: minX,
    y: minY,
    width: Math.max(10, maxX - minX),
    height: Math.max(10, maxY - minY),
  }
  layoutData.value.rooms = [...(layoutData.value.rooms || []), newRoom]
  addRoomModal.value = null
  saveLayoutData()
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
      await triggerAutoGraph(false)
    } catch (err) {
      console.error('Ошибка удаления POI:', err)
    }
  } else if (type === 'wall') {
    layoutData.value.walls = (layoutData.value.walls || []).filter(w => w.id !== item.id)
    await saveLayoutData()
  } else if (type === 'room') {
    layoutData.value.rooms = (layoutData.value.rooms || []).filter(r => r.id !== item.id)
    await saveLayoutData()
  } else if (type === 'obstacle') {
    layoutData.value.obstacles = (layoutData.value.obstacles || []).filter(o => o.id !== item.id)
    await saveLayoutData()
  } else if (type === 'corridor') {
    layoutData.value.corridors = (layoutData.value.corridors || []).filter(c => c.id !== item.id)
    await saveLayoutData()
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
  calibrating.value = true
  calibPoints = []
  calibResult.value = null
  if (calibLayer) calibLayer.clearLayers()
}

function handleCalibClick(lat, lng) {
  if (!window.L || !calibLayer) return
  calibPoints.push({ lat, lng })
  const dot = window.L.circleMarker([lat, lng], { radius: 5, color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 1 })
  calibLayer.addLayer(dot)

  if (calibPoints.length === 2) {
    const dx = calibPoints[1].lng - calibPoints[0].lng
    const dy = calibPoints[1].lat - calibPoints[0].lat
    const pixels = Math.sqrt(dx * dx + dy * dy)
    calibResult.value = { pixels }
    window.L.polyline([[calibPoints[0].lat, calibPoints[0].lng], [calibPoints[1].lat, calibPoints[1].lng]], { color: '#f59e0b', weight: 2 }).addTo(calibLayer)
    calibrating.value = false
  }
}

async function saveCalibration() {
  if (!calibResult.value || !calibDistance.value) return
  const ppm = calibResult.value.pixels / parseFloat(calibDistance.value)
  try {
    await floorsApi.update(currentFloor.value.id, { ppm })
    currentFloor.value.ppm = ppm
    currentFloor.value.pixels_per_meter = ppm
    calibResult.value = null
    calibDistance.value = ''
    calibLayer?.clearLayers()
    alert(`Масштаб сохранён: ${ppm.toFixed(2)} px/м`)
  } catch (e) {
    console.error('Ошибка сохранения масштаба:', e)
  }
}

// Event handlers
async function onPoiAdded() {
  addPoiModal.value = null
  await loadFloorData()
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

function toggleShowGraph(val) {
  showGraph.value = val
  drawNavGraph()
}

function nudgeSelected(dx, dy) {
  if (!selectedElement.value) return
  const { type, item } = selectedElement.value
  if (type === 'room' || (type === 'obstacle' && item.type === 'rect')) {
    item.x = Math.round(item.x + dx)
    item.y = Math.round(item.y + dy)
    saveLayoutData(true)
  } else if (type === 'obstacle' && item.type === 'circle') {
    item.x = Math.round(item.x + dx)
    item.y = Math.round(item.y + dy)
    saveLayoutData(true)
  } else if (type === 'wall' || type === 'corridor') {
    item.x1 = Math.round(item.x1 + dx)
    item.y1 = Math.round(item.y1 + dy)
    item.x2 = Math.round(item.x2 + dx)
    item.y2 = Math.round(item.y2 + dy)
    saveLayoutData(true)
  } else if (type === 'poi') {
    const px = Math.round(Number(item.x_coord ?? item.x ?? 0) + dx)
    const py = Math.round(Number(item.y_coord ?? item.y ?? 0) + dy)
    item.x_coord = px
    item.y_coord = py
    item.x = px
    item.y = py
    poisApi.update(item.id, { x_coord: px, y_coord: py }).then(() => {
      triggerAutoGraph(false)
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
      if (selectedElement.value && mode.value === 'view') {
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
  } else if (e.key === 'Escape') {
    if (drawingPoint.value) {
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
        :showGraph="showGraph"
        :graphStats="graphStats"
        :generatingGraph="generatingGraph"
        :layoutCounts="layoutCounts"
        v-model:calibDistance="calibDistance"
        @select-floor="onFloorSelected"
        @floor-created="onFloorCreated"
        @upload-plan="showUpload = true; isMobileSidebarOpen = false"
        @set-mode="mode = $event; cancelDrawing(); selectedElement = null; isMobileSidebarOpen = false"
        @auto-graph="triggerAutoGraph(true)"
        @toggle-show-graph="toggleShowGraph"
        @update:blueprintOpacity="updateBlueprintOpacity"
        @clear-layout="handleClearLayout"
        @start-calib="startCalibration; isMobileSidebarOpen = false"
        @save-calib="saveCalibration"
        @cancel-calib="calibrating = false; calibPoints = []; calibLayer?.clearLayers(); calibResult = null"
        @delete-plan="onDeletePlan"
        @close-mobile="isMobileSidebarOpen = false"
      />
    </div>

    <!-- Map Area -->
    <div class="flex-1 relative overflow-hidden architectural-canvas" style="background: #070c18">
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
        <span v-if="drawingPoint" class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping shrink-0"></span>
        <span v-else class="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse shrink-0"></span>

        <span v-if="mode === 'room' && !drawingPoint" class="text-slate-100 truncate">Кликните первый угол зоны</span>
        <span v-if="mode === 'room' && drawingPoint" class="text-amber-300 truncate">Кликните второй угол для завершения зоны</span>

        <span v-if="mode === 'wall' && !drawingPoint" class="text-slate-100 truncate">Кликните начальную точку стены</span>
        <span v-if="mode === 'wall' && drawingPoint" class="text-amber-300 truncate">Кликните конечную точку стены</span>

        <span v-if="mode === 'circle'" class="text-slate-100 truncate">Кликните для установки колонны</span>

        <span v-if="mode === 'rect' && !drawingPoint" class="text-slate-100 truncate">Кликните первый угол препятствия</span>
        <span v-if="mode === 'rect' && drawingPoint" class="text-amber-300 truncate">Кликните второй угол препятствия</span>

        <span v-if="mode === 'corridor' && !drawingPoint" class="text-slate-100 truncate">Кликните начало коридора</span>
        <span v-if="mode === 'corridor' && drawingPoint" class="text-amber-300 truncate">Кликните конец коридора</span>

        <span v-if="mode === 'poi'" class="text-slate-100 truncate">Кликните для установки POI</span>

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

      <!-- Calibration Indicator -->
      <div v-if="calibrating" class="absolute top-4 left-1/2 -translate-x-1/2 z-10 card-glass px-4 py-2 text-sm font-medium text-amber-400 border border-amber-500/30">
        🎯 {{ calibPoints.length === 0 ? 'Кликните первую точку' : 'Кликните вторую точку' }}
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

    <!-- Add Room Modal -->
    <div v-if="addRoomModal" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div class="card w-full max-w-sm p-5 space-y-4 shadow-2xl border border-slate-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <Square :size="18" class="text-blue-400" />
            <h3 class="font-semibold text-white text-sm">Новая зона / комната</h3>
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
.room-title-tag {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94a3b8;
  background: rgba(15, 23, 42, 0.85);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(71, 85, 105, 0.4);
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
  font-size: 9px;
  color: #cbd5e1;
  background: rgba(15, 23, 42, 0.8);
  padding: 1px 4px;
  border-radius: 3px;
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
