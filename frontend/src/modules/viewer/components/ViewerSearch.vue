<script setup lang="ts">
import { computed, ref } from 'vue'
import { Search, X, Building2, Utensils, Bath, Mic, Sparkles } from 'lucide-vue-next'
import type { POI, PoiCategory } from '../types'

interface Props {
  modelValue: string
  selectedCategory: PoiCategory | 'all'
  pois: POI[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'update:selectedCategory', category: PoiCategory | 'all'): void
  (e: 'selectPoi', poi: POI): void
}>()

const isFocused = ref(false)

const categories: { key: PoiCategory | 'all'; label: string; icon: any }[] = [
  { key: 'all', label: 'Все', icon: Sparkles },
  { key: 'stand', label: 'Стенды', icon: Building2 },
  { key: 'food', label: 'Еда', icon: Utensils },
  { key: 'wc', label: 'WC', icon: Bath },
  { key: 'stage', label: 'Сцена', icon: Mic },
]

const searchResults = computed(() => {
  const q = props.modelValue.trim().toLowerCase()
  if (!q) return []
  return props.pois.filter((poi) => {
    return (
      poi.title.toLowerCase().includes(q) ||
      poi.description.toLowerCase().includes(q) ||
      poi.category.toLowerCase().includes(q)
    )
  })
})

function onInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  emit('update:modelValue', val)
}

function clearSearch() {
  emit('update:modelValue', '')
}

function selectCategory(category: PoiCategory | 'all') {
  emit('update:selectedCategory', category)
}

function handleSelectPoi(poi: POI) {
  emit('selectPoi', poi)
  emit('update:modelValue', '')
  isFocused.value = false
}
</script>

<template>
  <div class="relative w-full flex flex-col gap-2.5 z-30 pointer-events-auto">
    <!-- Строка поиска -->
    <div class="relative w-full">
      <div
        class="flex items-center gap-3 px-3.5 py-2.5 rounded-2xl bg-slate-900/90 backdrop-blur-md border border-slate-800 shadow-xl shadow-black/40 transition-all focus-within:border-blue-500/80 focus-within:ring-2 focus-within:ring-blue-500/20"
      >
        <Search class="w-5 h-5 text-slate-400 shrink-0" />
        <input
          :value="modelValue"
          type="text"
          placeholder="Поиск стенда, кофе, сцены, WC..."
          class="w-full bg-transparent text-sm text-slate-100 placeholder-slate-400 outline-none"
          @input="onInput"
          @focus="isFocused = true"
          @blur="setTimeout(() => (isFocused = false), 200)"
        />
        <button
          v-if="modelValue"
          type="button"
          class="p-1 rounded-full text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          @click="clearSearch"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Выпадающий список результатов поиска -->
      <transition
        enter-active-class="transition duration-150 ease-out"
        enter-from-class="transform -translate-y-2 opacity-0"
        enter-to-class="transform translate-y-0 opacity-100"
        leave-active-class="transition duration-100 ease-in"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="isFocused && searchResults.length > 0"
          class="absolute top-full left-0 right-0 mt-2 max-h-64 overflow-y-auto rounded-2xl bg-slate-900/95 backdrop-blur-xl border border-slate-800 shadow-2xl p-2 flex flex-col gap-1 z-40 divide-y divide-slate-800/60"
        >
          <button
            v-for="poi in searchResults"
            :key="poi.id"
            type="button"
            class="flex items-center gap-3 p-2.5 rounded-xl text-left hover:bg-slate-800/80 transition-colors group"
            @mousedown="handleSelectPoi(poi)"
          >
            <div
              class="w-8 h-8 rounded-full flex items-center justify-center shrink-0 text-white text-xs font-semibold"
              :class="{
                'bg-blue-600': poi.category === 'stand',
                'bg-amber-600': poi.category === 'food',
                'bg-cyan-600': poi.category === 'wc',
                'bg-purple-600': poi.category === 'stage',
                'bg-emerald-600': poi.category === 'entrance',
                'bg-sky-600': poi.category === 'wifi',
                'bg-slate-600': poi.category === 'info',
              }"
            >
              {{ poi.category.toUpperCase().slice(0, 2) }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-slate-100 truncate group-hover:text-blue-400">
                {{ poi.title }}
              </div>
              <div class="text-xs text-slate-400 truncate">
                {{ poi.description }}
              </div>
            </div>
          </button>
        </div>
      </transition>
    </div>

    <!-- Чипсы категорий -->
    <div class="flex items-center gap-2 overflow-x-auto no-scrollbar py-0.5 -mx-1 px-1">
      <button
        v-for="cat in categories"
        :key="cat.key"
        type="button"
        class="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium shrink-0 transition-all cursor-pointer shadow-sm select-none"
        :class="[
          selectedCategory === cat.key
            ? 'bg-blue-600 text-white shadow-blue-600/30 shadow-md ring-1 ring-blue-400'
            : 'bg-slate-900/90 text-slate-300 hover:text-white hover:bg-slate-800 border border-slate-800 backdrop-blur-md',
        ]"
        @click="selectCategory(cat.key)"
      >
        <component :is="cat.icon" class="w-3.5 h-3.5" />
        <span>{{ cat.label }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* Скрытие нативного скроллбара */
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
.no-scrollbar {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
