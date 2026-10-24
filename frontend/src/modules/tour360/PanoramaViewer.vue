<template>
  <PanoramaViewer
    :panorama-url="props.panoramaUrl"
    :image-path="props.imagePath"
    :poi="props.poi"
    :hot-spots="props.hotSpots"
    :title="props.title"
    :compass="true"
    @hotspot-click="(hs) => emit('hotspotClick', hs)"
  />
</template>

<script setup lang="ts">
import PanoramaViewer, { type HotSpotItem } from '../viewer/components/PanoramaViewer.vue'
import type { POI } from '../viewer/types'

interface Props {
  panoramaUrl?: string | null
  imagePath?: string | null
  poi?: POI | null
  hotSpots?: HotSpotItem[]
  title?: string
}

const props = withDefaults(defineProps<Props>(), {
  panoramaUrl: '/hall_360_panorama.jpg',
  imagePath: null,
  poi: null,
  hotSpots: () => [],
  title: 'Выставка: Холл ТТК 360°',
})

const emit = defineEmits<{
  (e: 'hotspotClick', hotspot: HotSpotItem): void
}>()
</script>
