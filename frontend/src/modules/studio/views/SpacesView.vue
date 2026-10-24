<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { spacesApi, floorsApi } from '../../../api'
import SpaceCard from '../components/SpaceCard.vue'
import CreateSpaceModal from '../components/CreateSpaceModal.vue'
import { Plus, RefreshCw } from 'lucide-vue-next'

const router = useRouter()
const spaces = ref([])
const loading = ref(false)
const showCreateModal = ref(false)

async function fetchSpaces() {
  loading.value = true
  try {
    const { data } = await spacesApi.list()
    spaces.value = Array.isArray(data) ? data : (data.items || [])
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function handleTogglePublish(space) {
  try {
    if (space.is_published) {
      await spacesApi.unpublish(space.id)
    } else {
      await spacesApi.publish(space.id)
    }
    await fetchSpaces()
  } catch (e) {
    console.error(e)
  }
}

async function handleDelete(spaceId) {
  if (!confirm('Удалить это пространство?')) return
  try {
    await spacesApi.delete(spaceId)
    await fetchSpaces()
  } catch (e) {
    console.error(e)
  }
}

function handleOpenEditor(space) {
  // Need to load floors for this space and open first floor editor
  openEditorForSpace(space)
}

async function openEditorForSpace(space) {
  try {
    const { data } = await floorsApi.list(space.id)
    const floors = Array.isArray(data) ? data : (data.items || [])
    if (floors.length > 0) {
      router.push(`/admin/spaces/${space.id}/floors/${floors[0].id}/editor`)
    } else {
      // Create first floor automatically
      const { data: floor } = await floorsApi.create(space.id, { name: 'Этаж 1', level: 1 })
      router.push(`/admin/spaces/${space.id}/floors/${floor.id}/editor`)
    }
  } catch (e) {
    console.error(e)
  }
}

function onSpaceCreated() {
  showCreateModal.value = false
  fetchSpaces()
}

onMounted(fetchSpaces)
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex items-center justify-between mb-8 fade-in">
      <div>
        <h1 class="text-2xl font-bold" style="color: var(--text-primary)">Мои пространства</h1>
        <p class="text-sm mt-1" style="color: var(--text-muted)">Управляйте мероприятиями, зданиями и выставочными площадками</p>
      </div>
      <div class="flex items-center gap-3">
        <button id="refresh-spaces" @click="fetchSpaces" class="btn btn-ghost" :class="{ 'opacity-50': loading }">
          <RefreshCw :size="15" :class="loading ? 'animate-spin' : ''" />
        </button>
        <button id="create-space-btn" @click="showCreateModal = true" class="btn btn-primary">
          <Plus :size="16" />
          Новое пространство
        </button>
      </div>
    </div>

    <!-- Loading skeleton -->
    <div v-if="loading && spaces.length === 0" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
      <div v-for="i in 3" :key="i" class="skeleton h-52 rounded-xl"></div>
    </div>

    <!-- Empty state -->
    <div v-else-if="!loading && spaces.length === 0" class="flex flex-col items-center justify-center py-24 text-center fade-in">
      <div class="w-20 h-20 rounded-2xl mb-6 flex items-center justify-center" style="background: var(--bg-surface)">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color: var(--text-muted)">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
      </div>
      <h2 class="text-lg font-semibold mb-2" style="color: var(--text-primary)">Нет пространств</h2>
      <p class="text-sm mb-6 max-w-xs" style="color: var(--text-muted)">Создайте первое пространство и начните оцифровывать ваше здание или мероприятие</p>
      <button @click="showCreateModal = true" class="btn btn-primary">
        <Plus :size="16" />
        Создать пространство
      </button>
    </div>

    <!-- Spaces grid -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
      <SpaceCard
        v-for="space in spaces"
        :key="space.id"
        :space="space"
        @toggle-publish="handleTogglePublish(space)"
        @delete="handleDelete(space.id)"
        @open-editor="handleOpenEditor(space)"
        class="fade-in"
      />
    </div>

    <!-- Create modal -->
    <CreateSpaceModal
      v-if="showCreateModal"
      @close="showCreateModal = false"
      @created="onSpaceCreated"
    />
  </div>
</template>
