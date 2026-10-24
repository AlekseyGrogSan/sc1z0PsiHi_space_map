<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { floorsApi, poisApi, navApi, spacesApi } from '../../../api'
import FloorSidebar from '../components/FloorSidebar.vue'
import PlanUploadPanel from '../components/PlanUploadPanel.vue'
import AddPoiModal from '../components/AddPoiModal.vue'
import AddNodeModal from '../components/AddNodeModal.vue'
import { ArrowLeft, Layers } from 'lucide-vue-next'

const props = defineProps({ spaceId: String, floorId: String })
const router = useRouter()

// State
const space = ref(null)
const floors = ref([])
const currentFloor = ref(null)
const pois = ref([])
const navNodes = ref([])
const navEdges = ref([])
const loading = ref(true)
const mode = ref('view') // 'view' | 'poi' | 'nav'
const showUpload = ref(false)
const addPoiModal = ref(null)   // { x, y } in pixel coords
const addNodeModal = ref(null)  // { x, y }
const selectedNode = ref(null)  // first node for edge creation

// Leaflet
let map = null
let poiLayer = null
let navLayer = null
let edgeLayer = null
let calibPoints = []
let calibLayer = null
const mapReady = ref(false)
const calibrating = ref(false)
const savingGraph = ref(false)
let syncTimer = null

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
  const [poisRes, graphRes] = await Promise.allSettled([
    poisApi.list(fid),
    navApi.getGraph(fid),
  ])
  pois.value = poisRes.status === 'fulfilled' ? (Array.isArray(poisRes.value.data) ? poisRes.value.data : (poisRes.value.data?.items || [])) : []
  
  if (graphRes.status === 'fulfilled' && graphRes.value?.data) {
    const g = graphRes.value.data
    navNodes.value = (g.nodes || []).map((n, idx) => ({
      ...n,
      ref: n.ref || `n_${n.id || idx}`,
    }))
    navEdges.value = g.edges || []
  } else {
    navNodes.value = []
    navEdges.value = []
  }
  if (map) refreshMapLayers()
}

// Initialize Leaflet
async function initMap() {
  const L = (await import('leaflet')).default
  await import('leaflet/dist/leaflet.css')

  if (map) { map.remove(); map = null }

  const floor = currentFloor.value
  const planUrl = floor?.plan_url || floor?.plan_image_url
  if (!planUrl) {
    mapReady.value = true
    return
  }

  const img = new Image()
  img.onload = () => {
    const w = img.naturalWidth
    const h = img.naturalHeight

    map = L.map('floor-map', {
      crs: L.CRS.Simple,
      minZoom: -3,
      maxZoom: 3,
      zoomSnap: 0.25,
      attributionControl: false,
    })

    const bounds = [[0, 0], [h, w]]
    L.imageOverlay(planUrl, bounds).addTo(map)
    map.fitBounds(bounds)

    poiLayer = L.layerGroup().addTo(map)
    navLayer = L.layerGroup().addTo(map)
    edgeLayer = L.layerGroup().addTo(map)
    calibLayer = L.layerGroup().addTo(map)

    map.on('click', onMapClick)
    mapReady.value = true
    refreshMapLayers()
  }
  img.onerror = () => { mapReady.value = true }
  img.src = planUrl
}

function refreshMapLayers() {
  if (!map) return
  drawPois()
  drawNavGraph()
}

const CATEGORY_EMOJI = {
  stand: '🏢', food: '☕', cafe: '☕', wc: '🚻', toilet: '🚻',
  wifi: '📶', info: 'ℹ️', stage: '🎤', entrance: '🚪', exit: '🚪',
  elevator: '🛗', stairs: '🪜', other: '📍',
}

function drawPois() {
  if (!poiLayer) return
  poiLayer.clearLayers()
  const L = window.L || null
  if (!L) return
  pois.value.forEach(poi => {
    const emoji = CATEGORY_EMOJI[poi.category] || '📍'
    const poiTitle = poi.title || poi.name || ''
    const icon = window.L.divIcon({
      className: '',
      html: `<div class="poi-marker" data-id="${poi.id}" title="${poiTitle}">${emoji}<span>${poiTitle}</span></div>`,
      iconAnchor: [16, 16],
    })
    const py = Number(poi.y_coord ?? poi.y ?? 0)
    const px = Number(poi.x_coord ?? poi.x ?? 0)
    const marker = window.L.marker([py, px], { icon, draggable: true })
    marker.on('dragend', async (e) => {
      const { lat, lng } = e.target.getLatLng()
      await poisApi.update(poi.id, { y_coord: lat, x_coord: lng })
    })
    marker.on('click', () => {
      if (mode.value === 'poi') return
    })
    poiLayer.addLayer(marker)
  })
}

function drawNavGraph() {
  if (!navLayer || !edgeLayer) return
  navLayer.clearLayers()
  edgeLayer.clearLayers()
  if (!window.L) return

  // Draw edges
  navEdges.value.forEach(edge => {
    const fromNode = navNodes.value.find(n => n.id === edge.from_node_id || (edge.from_ref && n.ref === edge.from_ref))
    const toNode = navNodes.value.find(n => n.id === edge.to_node_id || (edge.to_ref && n.ref === edge.to_ref))
    if (!fromNode || !toNode) return

    const fy = Number(fromNode.y ?? fromNode.y_coord ?? 0)
    const fx = Number(fromNode.x ?? fromNode.x_coord ?? 0)
    const ty = Number(toNode.y ?? toNode.y_coord ?? 0)
    const tx = Number(toNode.x ?? toNode.x_coord ?? 0)

    const line = window.L.polyline(
      [[fy, fx], [ty, tx]],
      { color: '#3b82f6', weight: 2, opacity: 0.8, dashArray: edge.is_accessible ? null : '5,5' }
    )
    line.on('click', () => {
      if (confirm('Удалить это ребро графа?')) {
        navEdges.value = navEdges.value.filter(e => e !== edge)
        refreshMapLayers()
        syncGraph()
      }
    })
    edgeLayer.addLayer(line)
  })

  // Draw nodes
  const nodeTypeColor = {
    walkway: '#64748b',
    corridor: '#64748b',
    door: '#f59e0b',
    stairs: '#8b5cf6',
    elevator: '#06b6d4',
    default: '#3b82f6'
  }
  navNodes.value.forEach(node => {
    const color = nodeTypeColor[node.node_type] || nodeTypeColor.default
    const icon = window.L.divIcon({
      className: '',
      html: `<div class="nav-node" style="background:${color}" data-id="${node.id || node.ref}" title="${node.node_type}"></div>`,
      iconAnchor: [8, 8],
    })
    const ny = Number(node.y ?? node.y_coord ?? 0)
    const nx = Number(node.x ?? node.x_coord ?? 0)
    const marker = window.L.marker([ny, nx], { icon, draggable: true })
    marker.on('click', () => onNavNodeClick(node))
    marker.on('dragend', (e) => {
      const { lat, lng } = e.target.getLatLng()
      node.y = lat
      node.x = lng
      node.y_coord = lat
      node.x_coord = lng
      refreshMapLayers()
      syncGraph()
    })
    navLayer.addLayer(marker)
  })
}

function syncGraph() {
  clearTimeout(syncTimer)
  syncTimer = setTimeout(async () => {
    if (!currentFloor.value) return
    savingGraph.value = true
    try {
      const nodeInputs = navNodes.value.map((n, idx) => {
        const refKey = n.ref || `n_${n.id || idx}`
        n.ref = refKey
        return {
          ref: refKey,
          id: n.id || undefined,
          x: Number(n.x ?? n.x_coord),
          y: Number(n.y ?? n.y_coord),
          node_type: n.node_type === 'corridor' ? 'walkway' : (n.node_type || 'walkway'),
          panorama_id: n.panorama_id || undefined,
        }
      })

      const edgeInputs = []
      const seen = new Set()
      for (const e of navEdges.value) {
        let fromRef = e.from_ref
        let toRef = e.to_ref
        if (!fromRef && e.from_node_id) {
          const fn = navNodes.value.find(n => n.id === e.from_node_id)
          fromRef = fn?.ref
        }
        if (!toRef && e.to_node_id) {
          const tn = navNodes.value.find(n => n.id === e.to_node_id)
          toRef = tn?.ref
        }
        if (fromRef && toRef && fromRef !== toRef) {
          const pairKey = [fromRef, toRef].sort().join('___')
          if (!seen.has(pairKey)) {
            seen.add(pairKey)
            edgeInputs.push({ from_ref: fromRef, to_ref: toRef })
          }
        }
      }

      const { data } = await navApi.saveGraph(currentFloor.value.id, {
        nodes: nodeInputs,
        edges: edgeInputs,
      })
      if (data?.graph) {
        navNodes.value = (data.graph.nodes || []).map((n, idx) => ({
          ...n,
          ref: n.ref || `n_${n.id || idx}`,
        }))
        navEdges.value = data.graph.edges || []
        refreshMapLayers()
      }
    } catch (err) {
      console.error('Ошибка сохранения навигационного графа:', err)
    } finally {
      savingGraph.value = false
    }
  }, 400)
}

function onMapClick(e) {
  if (!map) return
  const { lat, lng } = e.latlng

  if (calibrating.value) {
    handleCalibClick(lat, lng)
    return
  }

  if (mode.value === 'poi') {
    addPoiModal.value = { x: lng, y: lat }
  } else if (mode.value === 'nav') {
    addNodeModal.value = { x: lng, y: lat }
  }
}

function onNavNodeClick(node) {
  if (mode.value !== 'nav') return
  if (!selectedNode.value) {
    selectedNode.value = node
    return
  }
  if ((selectedNode.value.id && selectedNode.value.id === node.id) ||
      (selectedNode.value.ref && selectedNode.value.ref === node.ref)) {
    selectedNode.value = null
    return
  }
  // Create edge
  createEdge(selectedNode.value, node)
  selectedNode.value = null
}

function createEdge(from, to) {
  const fromRef = from.ref || (from.id ? `n_${from.id}` : '')
  const toRef = to.ref || (to.id ? `n_${to.id}` : '')
  from.ref = fromRef
  to.ref = toRef

  const exists = navEdges.value.some(e => {
    const fMatch = (e.from_node_id === from.id && e.to_node_id === to.id) || (e.from_ref === fromRef && e.to_ref === toRef)
    const rMatch = (e.from_node_id === to.id && e.to_node_id === from.id) || (e.from_ref === toRef && e.to_ref === fromRef)
    return fMatch || rMatch
  })
  if (exists) return

  navEdges.value.push({
    from_node_id: from.id,
    to_node_id: to.id,
    from_ref: fromRef,
    to_ref: toRef,
    is_accessible: true,
  })
  refreshMapLayers()
  syncGraph()
}

// Calibration
const calibResult = ref(null)
const calibDistance = ref('')

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
    // Draw line
    window.L.polyline([[calibPoints[0].lat, calibPoints[0].lng], [calibPoints[1].lat, calibPoints[1].lng]], { color: '#f59e0b', weight: 2 }).addTo(calibLayer)
    calibrating.value = false
  }
}

async function saveCalibration() {
  if (!calibResult.value || !calibDistance.value) return
  const ppm = calibResult.value.pixels / parseFloat(calibDistance.value)
  try {
    currentFloor.value.ppm = ppm
    currentFloor.value.pixels_per_meter = ppm
    calibResult.value = null
    calibDistance.value = ''
    calibLayer?.clearLayers()
    alert(`Масштаб сохранён: ${ppm.toFixed(2)} px/м`)
  } catch (e) {
    console.error(e)
  }
}

async function onPoiAdded() {
  addPoiModal.value = null
  await loadFloorData()
}

function onNodeAdded(nodeData) {
  const tempRef = 'n_' + Date.now() + '_' + Math.floor(Math.random() * 1000)
  navNodes.value.push({
    ref: tempRef,
    id: undefined,
    x: nodeData.x,
    y: nodeData.y,
    node_type: nodeData.node_type || 'walkway',
    is_accessible: nodeData.is_accessible ?? true,
  })
  addNodeModal.value = null
  refreshMapLayers()
  syncGraph()
}

async function onFloorSelected(floor) {
  if (floor.id === currentFloor.value?.id) return
  currentFloor.value = floor
  router.replace(`/admin/spaces/${props.spaceId}/floors/${floor.id}/editor`)
  const planUrl = floor.plan_url || floor.plan_image_url
  if (planUrl) {
    await nextTick()
    await initMap()
  } else {
    if (map) { map.remove(); map = null; mapReady.value = false }
  }
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
}

async function onFloorCreated(floor) {
  floors.value.push(floor)
  await onFloorSelected(floor)
}

onMounted(async () => {
  // Inject leaflet global for event handlers
  const L = (await import('leaflet')).default
  window.L = L
  await fetchData()
  await nextTick()
  if (currentFloor.value?.plan_url || currentFloor.value?.plan_image_url) {
    await initMap()
  } else {
    loading.value = false
    mapReady.value = true
  }
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
      :selectedNode="selectedNode"
      v-model:calibDistance="calibDistance"
      @select-floor="onFloorSelected"
      @floor-created="onFloorCreated"
      @upload-plan="showUpload = true"
      @set-mode="mode = $event"
      @start-calib="startCalibration"
      @save-calib="saveCalibration"
      @cancel-calib="calibrating = false; calibPoints = []; calibLayer?.clearLayers(); calibResult = null"
    />

    <!-- Map area -->
    <div class="flex-1 relative overflow-hidden" style="background: #070c18">
      <!-- Loading overlay -->
      <div v-if="loading" class="absolute inset-0 flex items-center justify-center z-10">
        <div class="flex flex-col items-center gap-3">
          <span class="spinner" style="width:32px;height:32px;border-width:3px;color:var(--accent)"></span>
          <p class="text-sm" style="color: var(--text-muted)">Загрузка...</p>
        </div>
      </div>

      <!-- No plan state -->
      <div v-else-if="!(currentFloor?.plan_url || currentFloor?.plan_image_url)" class="absolute inset-0 flex flex-col items-center justify-center gap-4 z-10">
        <div class="w-16 h-16 rounded-2xl flex items-center justify-center" style="background: var(--bg-surface)">
          <Layers :size="32" style="color: var(--text-muted)" />
        </div>
        <h3 class="font-semibold" style="color: var(--text-primary)">Нет плана этажа</h3>
        <p class="text-sm text-center max-w-xs" style="color: var(--text-muted)">Загрузите PNG, JPG, WebP или PDF чертёж этажа для начала работы</p>
        <button @click="showUpload = true" class="btn btn-primary">
          Загрузить план
        </button>
      </div>

      <!-- Leaflet map -->
      <div id="floor-map" class="w-full h-full" style="z-index:0"></div>

      <!-- Saving indicator -->
      <div v-if="savingGraph" class="absolute bottom-4 right-4 z-10 card-glass px-3 py-1.5 rounded-lg text-xs flex items-center gap-2" style="color: #60a5fa; background: rgba(15,23,42,0.85); border: 1px solid rgba(59,130,246,0.3)">
        <span class="spinner w-3 h-3"></span>
        <span>Синхронизация графа...</span>
      </div>

      <!-- Mode indicator -->
      <div v-if="mode !== 'view'" class="absolute top-4 left-1/2 -translate-x-1/2 z-10 card-glass px-4 py-2 flex items-center gap-2 text-sm font-medium">
        <span v-if="mode === 'poi'" class="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
        <span v-if="mode === 'nav' && !selectedNode" class="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></span>
        <span v-if="mode === 'nav' && selectedNode" class="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
        <span v-if="mode === 'poi'" style="color: var(--text-primary)">Кликните на план, чтобы добавить POI</span>
        <span v-if="mode === 'nav' && !selectedNode" style="color: var(--text-primary)">Кликните для создания узла или выберите существующий</span>
        <span v-if="mode === 'nav' && selectedNode" style="color: #fbbf24">Узел выбран — кликните второй узел для создания ребра</span>
        <button @click="mode = 'view'; selectedNode = null" class="ml-2 text-xs" style="color: var(--text-muted)">✕ Отмена</button>
      </div>

      <!-- Calibration indicator -->
      <div v-if="calibrating" class="absolute top-4 left-1/2 -translate-x-1/2 z-10 card-glass px-4 py-2 text-sm font-medium" style="color: #fbbf24">
        🎯 {{ calibPoints.length === 0 ? 'Кликните первую точку' : 'Кликните вторую точку' }}
      </div>
    </div>

    <!-- Upload panel -->
    <PlanUploadPanel
      v-if="showUpload && currentFloor"
      :floorId="currentFloor.id"
      @close="showUpload = false"
      @uploaded="onPlanUploaded"
    />

    <!-- Add POI modal -->
    <AddPoiModal
      v-if="addPoiModal && currentFloor"
      :floorId="currentFloor.id"
      :coords="addPoiModal"
      @close="addPoiModal = null"
      @created="onPoiAdded"
    />

    <!-- Add Nav Node modal -->
    <AddNodeModal
      v-if="addNodeModal && currentFloor"
      :floorId="currentFloor.id"
      :coords="addNodeModal"
      @close="addNodeModal = null"
      @created="onNodeAdded"
    />
  </div>
</template>

<style>
/* Leaflet overrides */
.leaflet-container { background: #070c18; }

.poi-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  user-select: none;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.6));
}
.poi-marker span {
  font-size: 10px;
  background: rgba(15,23,42,0.9);
  color: #f1f5f9;
  padding: 1px 5px;
  border-radius: 4px;
  white-space: nowrap;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  border: 1px solid rgba(51,65,85,0.5);
}
.nav-node {
  width: 16px; height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.3);
  cursor: pointer;
  transition: transform 0.1s;
}
.nav-node:hover { transform: scale(1.4); }
</style>
