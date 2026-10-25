<script setup>
import { reactive, ref } from 'vue'
import { panoramaApi } from '../../../api'
import { X, Camera, Upload, AlertCircle } from 'lucide-vue-next'

const props = defineProps({
  floorId: [String, Number],
  coords: Object, // { x, y }
})
const emit = defineEmits(['close', 'created'])

const form = reactive({
  title: 'Панорама 360°',
  heading: 0,
})

const selectedFile = ref(null)
const previewUrl = ref('')
const loading = ref(false)
const error = ref('')

function onFileChange(e) {
  const file = e.target.files?.[0]
  if (file) {
    selectedFile.value = file
    previewUrl.value = URL.createObjectURL(file)
  }
}

function onDrop(e) {
  e.preventDefault()
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) {
    selectedFile.value = file
    previewUrl.value = URL.createObjectURL(file)
  }
}

async function handleUpload() {
  if (!selectedFile.value) {
    error.value = 'Пожалуйста, выберите файл 360° панорамы'
    return
  }
  loading.value = true
  error.value = ''

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('title', form.title || 'Панорама 360°')
    formData.append('x_coord', props.coords.x)
    formData.append('y_coord', props.coords.y)
    formData.append('initial_heading', Number(form.heading) || 0)

    await panoramaApi.upload(props.floorId, formData)
    emit('created')
  } catch (err) {
    console.error('Ошибка загрузки панорамы:', err)
    error.value = err.response?.data?.detail || 'Не удалось загрузить панораму'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center p-4" style="background: rgba(0,0,0,0.7); backdrop-filter: blur(4px)">
    <div class="card w-full max-w-md p-6 slide-up bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl text-slate-100" @click.stop>
      <div class="flex items-center justify-between mb-5">
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center border border-purple-500/30">
            <Camera :size="18" />
          </div>
          <div>
            <h3 class="font-semibold text-base text-white">Добавить 360° панораму</h3>
            <p class="text-xs text-slate-400">Установка точки сферического фототура</p>
          </div>
        </div>
        <button @click="$emit('close')" class="btn btn-ghost p-1.5 text-slate-400 hover:text-white"><X :size="16" /></button>
      </div>

      <form @submit.prevent="handleUpload" class="space-y-4">
        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1">Название точки / локации *</label>
          <input
            v-model="form.title"
            type="text"
            class="input w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-purple-500"
            placeholder="Центральный холл / Стенд 4"
            required
            autofocus
          />
        </div>

        <div>
          <label class="block text-xs font-medium text-slate-300 mb-1">Сферическое 360° фото (эквидистантное) *</label>
          <div
            class="border-2 border-dashed border-slate-700 hover:border-purple-500 rounded-xl p-4 text-center cursor-pointer transition-colors bg-slate-800/40 relative"
            @dragover.prevent
            @drop="onDrop"
            @click="$refs.fileInput.click()"
          >
            <input
              ref="fileInput"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              class="hidden"
              @change="onFileChange"
            />

            <div v-if="!selectedFile" class="flex flex-col items-center justify-center py-2">
              <Upload class="text-purple-400 mb-2" :size="24" />
              <p class="text-sm font-medium text-slate-200">Перетащите 360° фото или кликните</p>
              <p class="text-xs text-slate-400 mt-1">Поддерживаются JPG, PNG, WebP (2:1 соотношение)</p>
            </div>

            <div v-else class="flex items-center gap-3 text-left">
              <img
                v-if="previewUrl"
                :src="previewUrl"
                class="w-16 h-12 object-cover rounded border border-slate-600 shrink-0"
              />
              <div class="overflow-hidden">
                <p class="text-xs font-medium text-purple-300 truncate">{{ selectedFile.name }}</p>
                <p class="text-[11px] text-slate-400">{{ (selectedFile.size / 1024 / 1024).toFixed(2) }} МБ</p>
              </div>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-medium text-slate-300 mb-1">Координаты на плане</label>
            <div class="text-xs font-mono px-2.5 py-2 rounded bg-slate-800/80 border border-slate-700/60 text-slate-300">
              X: {{ coords.x.toFixed(0) }}, Y: {{ coords.y.toFixed(0) }}
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-300 mb-1">Азимут камеры (0..360°)</label>
            <input
              v-model.number="form.heading"
              type="number"
              min="0"
              max="360"
              class="input w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-1.5 text-xs text-white"
            />
          </div>
        </div>

        <div v-if="error" class="p-2.5 rounded-lg text-xs flex items-center gap-2 bg-red-900/30 text-red-300 border border-red-800/50">
          <AlertCircle :size="14" class="shrink-0" />
          <span>{{ error }}</span>
        </div>

        <div class="flex gap-3 pt-2">
          <button type="button" @click="$emit('close')" class="btn btn-ghost flex-1 justify-center text-sm py-2 text-slate-400 hover:text-white">
            Отмена
          </button>
          <button
            type="submit"
            :disabled="loading || !selectedFile"
            class="btn bg-purple-600 hover:bg-purple-500 text-white flex-1 justify-center text-sm py-2 rounded-xl font-medium shadow-lg shadow-purple-600/30 transition-all disabled:opacity-50 flex items-center gap-2"
          >
            <span v-if="loading" class="spinner w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
            {{ loading ? 'Обработка 360°...' : 'Создать панораму' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>
