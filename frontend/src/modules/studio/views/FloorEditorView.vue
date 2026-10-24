<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { floorsApi, poisApi, navApi, spacesApi } from '../../../api'
import FloorSidebar from '../components/FloorSidebar.vue'
import PlanUploadPanel from '../components/PlanUploadPanel.vue'
import AddPoiModal from '../components/AddPoiModal.vue'
import {
  ArrowLeft, Layers, Trash2, Check, X, Square, Minus, Circle, Box,
  Footprints, MapPin, Zap, Eye, RotateCcw
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
let graphLayer = null
let previewLayer = null
let calibLayer = null
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
  drawNavGraph()
}

// 1. Draw Rooms
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
    })

    rect.on('click', (e) => {
      if (mode.value === 'view') {
        L.DomEvent.stopPropagation(e)
        selectedElement.value = { type: 'room', item: r }
        refreshMapLayers()
      }
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

// 2. Draw Corridors
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
      }
    )
    poly.on('click', (e) => {
      if (mode.value === 'view') {
        L.DomEvent.stopPropagation(e)
        selectedElement.value = { type: 'corridor', item: c }
        refreshMapLayers()
      }
    })
    corridorsLayer.addLayer(poly)
  })
}

// 3. Draw Obstacles (Circular columns and rectangular booths)
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
      })
      circle.on('click', (e) => {
        if (mode.value === 'view') {
          L.DomEvent.stopPropagation(e)
          selectedElement.value = { type: 'obstacle', item: o }
          refreshMapLayers()
        }
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
      })
      rect.on('click', (e) => {
        if (mode.value === 'view') {
          L.DomEvent.stopPropagation(e)
          selectedElement.value = { type: 'obstacle', item: o }
          refreshMapLayers()
        }
      })
      obstaclesLayer.addLayer(rect)
    }
  })
}

// 4. Draw Walls
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
      }
    )
    wallLine.on('click', (e) => {
      if (mode.value === 'view') {
        L.DomEvent.stopPropagation(e)
        selectedElement.value = { type: 'wall', item: w }
        refreshMapLayers()
      }
    })
    wallsLayer.addLayer(wallLine)
  })
}

// 5. Draw POIs
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
      await poisApi.update(poi.id, { y_coord: lat, x_coord: lng })
      poi.y_coord = lat
      poi.x_coord = lng
      await triggerAutoGraph(false)
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

onMounted(async () => {
  await fetchData()
  await nextTick()
  await initMap()
})

onBeforeUnmount(() => {
  if (map) map.remove()
})
</script>

<template>
  <div class="flex h-full" style="height: calc(100vh - 56px)">
    <!-- Sidebar -->
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
      @upload-plan="showUpload = true"
      @set-mode="mode = $event; cancelDrawing(); selectedElement = null"
      @auto-graph="triggerAutoGraph(true)"
      @toggle-show-graph="toggleShowGraph"
      @update:blueprintOpacity="updateBlueprintOpacity"
      @clear-layout="handleClearLayout"
      @start-calib="startCalibration"
      @save-calib="saveCalibration"
      @cancel-calib="calibrating = false; calibPoints = []; calibLayer?.clearLayers(); calibResult = null"
    />

    <!-- Map Area -->
    <div class="flex-1 relative overflow-hidden architectural-canvas" style="background: #070c18">
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
      <div v-if="mode !== 'view'" class="absolute top-4 left-1/2 -translate-x-1/2 z-10 card-glass px-4 py-2 flex items-center gap-3 text-sm font-medium shadow-xl border border-slate-700/60 backdrop-blur-md">
        <span v-if="drawingPoint" class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping"></span>
        <span v-else class="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse"></span>

        <span v-if="mode === 'room' && !drawingPoint" class="text-slate-100">Кликните первый угол зоны/комнаты</span>
        <span v-if="mode === 'room' && drawingPoint" class="text-amber-300">Кликните противоположный угол для завершения зоны</span>

        <span v-if="mode === 'wall' && !drawingPoint" class="text-slate-100">Кликните начальную точку стены</span>
        <span v-if="mode === 'wall' && drawingPoint" class="text-amber-300">Кликните конечную точку стены</span>

        <span v-if="mode === 'circle'" class="text-slate-100">Кликните на карту, чтобы установить круглую колонну</span>

        <span v-if="mode === 'rect' && !drawingPoint" class="text-slate-100">Кликните первый угол препятствия</span>
        <span v-if="mode === 'rect' && drawingPoint" class="text-amber-300">Кликните второй угол препятствия</span>

        <span v-if="mode === 'corridor' && !drawingPoint" class="text-slate-100">Кликните начало прохода/коридора</span>
        <span v-if="mode === 'corridor' && drawingPoint" class="text-amber-300">Кликните конец прохода/коридора</span>

        <span v-if="mode === 'poi'" class="text-slate-100">Кликните на карте, чтобы поставить POI</span>

        <button @click="mode = 'view'; cancelDrawing()" class="btn btn-ghost px-2 py-0.5 text-xs text-slate-400 hover:text-white ml-1">
          ✕ Завершить
        </button>
      </div>

      <!-- Selected Element Floating Toolbar -->
      <div v-if="selectedElement && mode === 'view'" class="absolute bottom-6 left-1/2 -translate-x-1/2 z-10 card-glass px-4 py-2.5 flex items-center gap-4 text-xs font-medium shadow-2xl border border-slate-700 backdrop-blur-md rounded-xl">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-blue-400"></span>
          <span class="text-slate-300">Выбран элемент:</span>
          <b class="text-white capitalize">
            {{ selectedElement.type === 'room' ? `Зона "${selectedElement.item.title || 'Без названия'}"` : '' }}
            {{ selectedElement.type === 'wall' ? 'Стена' : '' }}
            {{ selectedElement.type === 'obstacle' ? `Препятствие "${selectedElement.item.title || selectedElement.item.type}"` : '' }}
            {{ selectedElement.type === 'corridor' ? 'Коридор' : '' }}
            {{ selectedElement.type === 'poi' ? `Точка "${selectedElement.item.title}"` : '' }}
          </b>
        </div>
        <div class="flex items-center gap-2">
          <button @click="deleteSelectedElement" class="btn btn-ghost text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 px-2 py-1 gap-1">
            <Trash2 :size="13" /> Удалить
          </button>
          <button @click="selectedElement = null; refreshMapLayers()" class="btn btn-ghost text-slate-400 px-2 py-1">
            ✕ Закрыть
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
</style>
