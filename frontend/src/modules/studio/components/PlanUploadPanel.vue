<script setup>
import { ref, reactive } from 'vue'
import { floorsApi } from '../../../api/index.js'
import { Upload, X, FileImage, CheckCircle } from 'lucide-vue-next'

const props = defineProps({ floorId: [String, Number] })
const emit = defineEmits(['close', 'uploaded'])

const isDragging = ref(false)
const file = ref(null)
const uploading = ref(false)
const progress = ref(0)
const error = ref('')
const done = ref(false)

function onDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer.files[0]
  if (f) setFile(f)
}

function onFileSelect(e) {
  const f = e.target.files[0]
  if (f) setFile(f)
}

function setFile(f) {
  const allowed = ['image/png', 'image/jpeg', 'image/webp', 'application/pdf']
  if (!allowed.includes(f.type)) {
    error.value = 'Поддерживаются PNG, JPG, WebP, PDF'
    return
  }
  error.value = ''
  file.value = f
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  error.value = ''
  progress.value = 0

  const formData = new FormData()
  formData.append('file', file.value)

  try {
    await floorsApi.uploadPlan(props.floorId, formData)
    done.value = true
    setTimeout(() => emit('uploaded'), 800)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Ошибка загрузки'
  } finally {
    uploading.value = false
  }
}

const sizeLabel = (bytes) => bytes > 1024 * 1024
  ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  : `${(bytes / 1024).toFixed(0)} KB`
</script>

<template>
  <!-- Overlay drawer from right -->
  <div class="fixed inset-0 z-40 flex justify-end" style="background: rgba(0,0,0,0.5); backdrop-filter: blur(2px)">
    <div class="flex flex-col w-full max-w-sm h-full slide-up" style="background: var(--bg-card); border-left: 1px solid var(--border)">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-4 border-b" style="border-color: var(--border)">
        <h3 class="font-semibold" style="color: var(--text-primary)">Загрузка плана этажа</h3>
        <button @click="$emit('close')" class="btn btn-ghost p-1.5"><X :size="18" /></button>
      </div>

      <div class="flex-1 overflow-y-auto px-5 py-5 space-y-5">
        <!-- Formats info -->
        <div class="flex items-start gap-2 p-3 rounded-lg text-xs" style="background: rgba(59,130,246,0.08); color: #60a5fa; border: 1px solid rgba(59,130,246,0.2)">
          <FileImage :size="14" class="shrink-0 mt-0.5" />
          <span>Поддерживаются форматы: <b>PNG, JPG, WebP, PDF</b>. Файл будет автоматически конвертирован бэкендом в WebP-тайлы.</span>
        </div>

        <!-- Drop zone -->
        <div
          class="relative flex flex-col items-center justify-center gap-3 p-8 rounded-xl cursor-pointer transition-all duration-200 text-center"
          :style="isDragging
            ? 'border: 2px dashed var(--accent); background: rgba(59,130,246,0.08);'
            : 'border: 2px dashed var(--border); background: var(--bg-surface);'"
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop.prevent="onDrop"
          @click="$refs.fileInput.click()"
        >
          <input ref="fileInput" type="file" class="hidden" accept=".png,.jpg,.jpeg,.webp,.pdf" @change="onFileSelect" />
          <div class="w-12 h-12 rounded-xl flex items-center justify-center transition-all" :style="isDragging ? 'background: rgba(59,130,246,0.2)' : 'background: var(--bg-card)'">
            <Upload :size="22" :style="isDragging ? 'color: var(--accent)' : 'color: var(--text-muted)'" />
          </div>
          <div>
            <p class="text-sm font-medium" style="color: var(--text-primary)">
              {{ isDragging ? 'Отпустите файл' : 'Перетащите файл или кликните' }}
            </p>
            <p class="text-xs mt-1" style="color: var(--text-muted)">PNG, JPG, WebP, PDF до 50 MB</p>
          </div>
        </div>

        <!-- Selected file -->
        <div v-if="file" class="flex items-center gap-3 p-3 rounded-lg" style="background: var(--bg-surface); border: 1px solid var(--border)">
          <FileImage :size="20" style="color: var(--accent)" class="shrink-0" />
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium truncate" style="color: var(--text-primary)">{{ file.name }}</p>
            <p class="text-xs" style="color: var(--text-muted)">{{ sizeLabel(file.size) }}</p>
          </div>
          <button @click="file = null" class="btn btn-ghost p-1"><X :size="14" /></button>
        </div>

        <!-- Progress -->
        <div v-if="uploading" class="space-y-2">
          <div class="h-1.5 rounded-full overflow-hidden" style="background: var(--bg-surface)">
            <div class="h-full rounded-full transition-all duration-300" style="background: var(--accent); width: 60%"></div>
          </div>
          <p class="text-xs text-center" style="color: var(--text-muted)">Загрузка и обработка...</p>
        </div>

        <!-- Done -->
        <div v-if="done" class="flex items-center justify-center gap-2 p-4 rounded-xl" style="background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.25); color: #34d399">
          <CheckCircle :size="20" />
          <span class="font-medium">План успешно загружен!</span>
        </div>

        <!-- Error -->
        <div v-if="error" class="p-3 rounded-lg text-sm" style="background: rgba(239,68,68,0.1); color: #f87171; border: 1px solid rgba(239,68,68,0.2)">
          {{ error }}
        </div>
      </div>

      <!-- Footer -->
      <div class="px-5 pb-5 pt-3 border-t flex gap-3" style="border-color: var(--border)">
        <button @click="$emit('close')" class="btn btn-ghost flex-1 justify-center">Отмена</button>
        <button
          id="upload-submit-btn"
          @click="upload"
          :disabled="!file || uploading || done"
          class="btn btn-primary flex-1 justify-center"
        >
          <span v-if="uploading" class="spinner w-4 h-4"></span>
          <Upload v-else :size="15" />
          {{ uploading ? 'Загрузка...' : 'Загрузить' }}
        </button>
      </div>
    </div>
  </div>
</template>
