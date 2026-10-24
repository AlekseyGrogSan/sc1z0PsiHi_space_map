<template>
  <div class="relative w-full h-screen bg-black flex items-center justify-center overflow-hidden">

    <video ref="videoElement" autoplay playsinline class="absolute inset-0 w-full h-full object-cover opacity-80"></video>


    <div class="relative z-10 w-64 h-64 border-4 rounded-full flex items-center justify-center"
         :class="isReadyToShoot ? 'border-green-500' : 'border-slate-500'">
      <div class="w-2 h-2 bg-red-500 rounded-full"></div>


      <div class="absolute top-4 text-white font-bold bg-slate-900/50 px-3 py-1 rounded">
        Yaw: {{ currentYaw }}°
      </div>
    </div>


    <div class="absolute bottom-10 flex flex-col items-center gap-4 w-full px-6 z-20">
      <button
        @click="captureFrame"
        :disabled="!isReadyToShoot"
        class="w-16 h-16 bg-[#e30613] rounded-full border-4 border-white shadow-xl disabled:opacity-50 disabled:bg-slate-400"
      >
        <CameraIcon class="w-6 h-6 text-white m-auto" />
      </button>
      <p class="text-white text-sm text-center">Когда кружок загорится зеленым — сделайте снимок[cite: 1]</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Camera as CameraIcon } from 'lucide-vue-next'

const videoElement = ref(null)
const currentYaw = ref(0)
const isReadyToShoot = ref(false)
let stream = null

onMounted(async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
    if (videoElement.value) {
      videoElement.value.srcObject = stream
    }


    window.addEventListener('deviceorientation', handleOrientation)
  } catch (error) {
    console.error("Ошибка доступа к камере:", error)
  }
})

const handleOrientation = (event) => {
  currentYaw.value = Math.round(event.alpha || 0)

  isReadyToShoot.value = currentYaw.value % 45 >= -2 && currentYaw.value % 45 <= 2
}
const captureFrame = async () => {
  if (!isReadyToShoot.value) return

  console.log("Кадр снят на угле", currentYaw.value)
}

onBeforeUnmount(() => {
  window.removeEventListener('deviceorientation', handleOrientation)
  if (stream) stream.getTracks().forEach(track => track.stop())
})
</script>