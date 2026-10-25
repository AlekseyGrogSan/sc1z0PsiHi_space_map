<script setup lang="ts">
import {
  Navigation, Rotate3d, X, Building2, Utensils, Bath, Mic, DoorOpen,
  DoorClosed, Wifi, Info, Armchair, Trash2, ShoppingBag, Gamepad2,
  Star, MapPin
} from 'lucide-vue-next'
import type { POI, PoiCategory } from '../types'

interface Props {
  poi: POI | null
  floorTitle?: string
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'buildRoute', poi: POI): void
  (e: 'setAsOrigin', poi: POI): void
  (e: 'openPanorama', poi: POI): void
}>()

const categoryInfo: Record<PoiCategory, { label: string; icon: any; color: string; badgeBg: string }> = {
  stand: { label: 'Стенд', icon: Building2, color: 'text-blue-400', badgeBg: 'bg-blue-500/10 border-blue-500/30' },
  retail: { label: 'Торговая точка', icon: ShoppingBag, color: 'text-sky-400', badgeBg: 'bg-sky-500/10 border-sky-500/30' },
  entertainment: { label: 'Развлечения', icon: Gamepad2, color: 'text-purple-400', badgeBg: 'bg-purple-500/10 border-purple-500/30' },
  food: { label: 'Еда и Кофе', icon: Utensils, color: 'text-amber-400', badgeBg: 'bg-amber-500/10 border-amber-500/30' },
  bench: { label: 'Лавочка', icon: Armchair, color: 'text-amber-300', badgeBg: 'bg-amber-600/10 border-amber-600/30' },
  trash: { label: 'Урна', icon: Trash2, color: 'text-slate-400', badgeBg: 'bg-slate-500/10 border-slate-500/30' },
  wc: { label: 'Санузел', icon: Bath, color: 'text-cyan-400', badgeBg: 'bg-cyan-500/10 border-cyan-500/30' },
  stage: { label: 'Сцена', icon: Mic, color: 'text-indigo-400', badgeBg: 'bg-indigo-500/10 border-indigo-500/30' },
  entrance: { label: 'Вход', icon: DoorOpen, color: 'text-emerald-400', badgeBg: 'bg-emerald-500/10 border-emerald-500/30' },
  exit: { label: 'Выход', icon: DoorClosed, color: 'text-red-400', badgeBg: 'bg-red-500/10 border-red-500/30' },
  wifi: { label: 'Wi-Fi', icon: Wifi, color: 'text-sky-400', badgeBg: 'bg-sky-500/10 border-sky-500/30' },
  info: { label: 'Инфокиоск', icon: Info, color: 'text-slate-300', badgeBg: 'bg-slate-500/10 border-slate-500/30' },
  custom: { label: 'Особая точка', icon: Star, color: 'text-teal-400', badgeBg: 'bg-teal-500/10 border-teal-500/30' },
}
</script>

<template>
  <transition
    enter-active-class="transform transition ease-out duration-300"
    enter-from-class="translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transform transition ease-in duration-200"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="translate-y-full opacity-0"
  >
    <div
      v-if="poi"
      class="w-full max-w-lg mx-auto bg-slate-900/95 backdrop-blur-xl border border-slate-800 rounded-3xl p-3.5 sm:p-5 shadow-2xl shadow-black/70 pointer-events-auto flex flex-col gap-3 sm:gap-4 text-slate-100 max-h-[85dvh] overflow-y-auto overscroll-contain"
    >
      <!-- Верхняя строка карточки: Категория, Этаж, Кнопка закрытия -->
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span
            class="flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-full text-[11px] sm:text-xs font-semibold border"
            :class="[categoryInfo[poi.category]?.badgeBg || 'bg-slate-800 border-slate-700', categoryInfo[poi.category]?.color || 'text-slate-200']"
          >
            <component :is="categoryInfo[poi.category]?.icon || Building2" class="w-3.5 h-3.5 shrink-0" />
            <span class="truncate">{{ categoryInfo[poi.category]?.label || poi.category }}</span>
          </span>

          <span v-if="floorTitle" class="text-[11px] sm:text-xs text-slate-400 font-medium truncate">
            • {{ floorTitle }}
          </span>
        </div>

        <button
          type="button"
          class="p-1.5 rounded-full text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors shrink-0"
          title="Закрыть карточку"
          @click="emit('close')"
        >
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Основной контент: Название, Описание и Логотип -->
      <div class="flex items-start gap-3 sm:gap-4">
        <!-- Логотип, если есть -->
        <div
          v-if="poi.logo_url"
          class="w-12 h-12 sm:w-14 sm:h-14 rounded-2xl bg-slate-800 border border-slate-700 overflow-hidden shrink-0 flex items-center justify-center p-1"
        >
          <img :src="poi.logo_url" :alt="poi.title" class="w-full h-full object-cover rounded-xl" />
        </div>

        <div class="flex-1 min-w-0">
          <h2 class="text-base sm:text-lg font-bold text-white tracking-tight leading-snug line-clamp-2">
            {{ poi.title }}
          </h2>
          <p class="text-xs sm:text-sm text-slate-300 mt-1 line-clamp-3 leading-relaxed">
            {{ poi.description || 'Описание отсутствует.' }}
          </p>
        </div>
      </div>

      <!-- Кнопки действий: компактная адаптивная сетка из 3 колонок -->
      <div class="grid grid-cols-3 gap-1.5 sm:gap-2 pt-1">
        <!-- Построить маршрут сюда -->
        <button
          type="button"
          class="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-2 sm:py-2.5 rounded-2xl bg-blue-600 hover:bg-blue-500 active:scale-98 text-white font-semibold text-[11px] sm:text-xs shadow-lg shadow-blue-600/30 transition-all cursor-pointer text-center leading-tight"
          @click="emit('buildRoute', poi)"
        >
          <Navigation class="w-3.5 h-3.5 fill-white shrink-0" />
          <span class="truncate">Маршрут</span>
        </button>

        <!-- Начать отсюда -->
        <button
          type="button"
          class="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-2 sm:py-2.5 rounded-2xl bg-emerald-600 hover:bg-emerald-500 active:scale-98 text-white font-semibold text-[11px] sm:text-xs shadow-lg shadow-emerald-600/30 transition-all cursor-pointer text-center leading-tight"
          @click="emit('setAsOrigin', poi)"
        >
          <MapPin class="w-3.5 h-3.5 shrink-0" />
          <span class="truncate">Старт</span>
        </button>

        <!-- Осмотреться в 360 -->
        <button
          v-if="poi.panorama_id"
          type="button"
          class="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-2 sm:py-2.5 rounded-2xl bg-slate-800 hover:bg-slate-700 active:scale-98 text-slate-100 border border-slate-700 font-semibold text-[11px] sm:text-xs transition-all cursor-pointer text-center leading-tight"
          @click="emit('openPanorama', poi)"
        >
          <Rotate3d class="w-3.5 h-3.5 text-purple-400 shrink-0" />
          <span class="truncate">Тур 360°</span>
        </button>
        <button
          v-else
          type="button"
          disabled
          class="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-2 sm:py-2.5 rounded-2xl bg-slate-900/50 text-slate-500 border border-slate-800/60 font-medium text-[11px] sm:text-xs text-center leading-tight cursor-not-allowed opacity-60"
          title="Для этой точки панорама 360° отсутствует"
        >
          <Rotate3d class="w-3.5 h-3.5 text-slate-600 shrink-0" />
          <span class="truncate">Нет 360°</span>
        </button>
      </div>
    </div>
  </transition>
</template>
