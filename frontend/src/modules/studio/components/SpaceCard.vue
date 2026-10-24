<script setup>
import { ref, computed, onMounted } from 'vue'
import { Pencil, Trash2, Globe, EyeOff, QrCode, ExternalLink, ChevronRight, Layers } from 'lucide-vue-next'
import QRCode from 'qrcode'

const props = defineProps({
  space: { type: Object, required: true },
})
const emit = defineEmits(['toggle-publish', 'delete', 'open-editor'])

const qrDataUrl = ref('')
const showQr = ref(false)
const publicUrl = computed(() => `${window.location.origin}/space/${props.space.slug}`)

async function generateQr() {
  try {
    qrDataUrl.value = await QRCode.toDataURL(publicUrl.value, {
      width: 200,
      margin: 1,
      color: { dark: '#f1f5f9', light: '#0f172a' },
    })
    showQr.value = true
  } catch (e) {
    console.error(e)
  }
}

const badgeClass = computed(() =>
  props.space.is_published ? 'badge-green' : 'badge-slate'
)
const badgeLabel = computed(() =>
  props.space.is_published ? 'Опубликовано' : 'Черновик'
)
</script>

<template>
  <div class="card flex flex-col p-5 gap-4 group hover:border-slate-600 transition-all duration-200">
    <!-- Header row -->
    <div class="flex items-start justify-between gap-2">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 mb-1 flex-wrap">
          <span :class="['badge', badgeClass]">
            <span class="w-1.5 h-1.5 rounded-full" :style="space.is_published ? 'background:#34d399' : 'background:#64748b'"></span>
            {{ badgeLabel }}
          </span>
        </div>
        <h3 class="font-semibold text-base leading-tight truncate" style="color: var(--text-primary)">{{ space.name }}</h3>
        <p class="text-xs mt-0.5 font-mono truncate" style="color: var(--text-muted)">{{ space.slug }}</p>
      </div>

      <!-- Actions -->
      <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button :id="`space-qr-${space.id}`" @click="generateQr" class="btn btn-ghost p-2 text-xs" title="QR-код">
          <QrCode :size="15" />
        </button>
        <button :id="`space-delete-${space.id}`" @click="$emit('delete')" class="btn btn-ghost p-2 text-xs hover:text-red-400" title="Удалить">
          <Trash2 :size="15" />
        </button>
      </div>
    </div>

    <!-- Description -->
    <p v-if="space.description" class="text-sm line-clamp-2" style="color: var(--text-secondary)">{{ space.description }}</p>

    <!-- QR panel -->
    <div v-if="showQr" class="flex flex-col items-center gap-3 p-4 rounded-xl" style="background: var(--bg-surface)">
      <img :src="qrDataUrl" alt="QR code" class="rounded-lg" style="width:140px;height:140px" />
      <p class="text-xs text-center break-all" style="color: var(--text-muted)">{{ publicUrl }}</p>
      <a :href="publicUrl" target="_blank" class="btn btn-ghost text-xs py-1 px-3 gap-1">
        <ExternalLink :size="12" />
        Открыть
      </a>
      <button @click="showQr = false" class="text-xs" style="color: var(--text-muted)">Скрыть</button>
    </div>

    <hr class="divider" />

    <!-- Footer actions -->
    <div class="flex items-center gap-2">
      <button
        :id="`space-publish-${space.id}`"
        @click="$emit('toggle-publish')"
        class="btn text-xs py-1.5 px-3 flex-1 justify-center"
        :class="space.is_published ? 'btn-ghost' : 'btn-primary'"
      >
        <Globe v-if="!space.is_published" :size="13" />
        <EyeOff v-else :size="13" />
        {{ space.is_published ? 'Снять с публикации' : 'Опубликовать' }}
      </button>

      <button
        :id="`space-editor-${space.id}`"
        @click="$emit('open-editor')"
        class="btn btn-ttk text-xs py-1.5 px-4 gap-1.5"
      >
        <Layers :size="13" />
        Редактор
        <ChevronRight :size="13" />
      </button>
    </div>
  </div>
</template>
