<template>
  <div class="relative w-full h-screen bg-slate-950 text-white flex flex-col">

    <div id="panorama" class="w-full h-full"></div>


    <div class="absolute bottom-6 right-6 flex gap-4">
      <button
        @click="toggleGyroscope"
        class="p-3 bg-slate-900 rounded-full shadow-lg hover:bg-slate-800 transition text-[#3b82f6]"
      >
        <CompassIcon class="w-6 h-6" />
      </button>
    </div>

    <div class="absolute top-4 left-4 bg-slate-900/80 p-3 rounded-xl backdrop-blur-sm">
      <h2 class="text-lg font-bold">Выставка: Холл</h2>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { Compass as CompassIcon } from 'lucide-vue-next'

const viewer = ref(null)

onMounted(() => {
  viewer.value = window.pannellum.viewer('panorama', {
    type: 'cubemap',
    cubemap: [
      '/cubemap/l1/f_0_0.webp',
      '/cubemap/l1/r_0_0.webp',
      '/cubemap/l1/b_0_0.webp',
      '/cubemap/l1/l_0_0.webp',
      '/cubemap/l1/u_0_0.webp',
      '/cubemap/l1/d_0_0.webp'
    ],
    autoLoad: true,
    compass: true,
    hotSpots: [
      {
        pitch: 14.1,
        yaw: 1.5,
        type: "info",
        text: "Стенд ТТК", // Information points
        URL: "#"
      },
      {
        pitch: -9.4,
        yaw: 222.6,
        type: "scene",
        text: "Переход в коридор",
        sceneId: "scene2"
      }
    ]
  })
})

const toggleGyroscope = () => {
  //gyroscope
  if (viewer.value) {
    viewer.value.toggleOrientation()
  }
}

onBeforeUnmount(() => {
  if (viewer.value) viewer.value.destroy()
})
</script>