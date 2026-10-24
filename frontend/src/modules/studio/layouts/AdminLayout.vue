<script setup>
import { useRouter } from 'vue-router'
import { LayoutGrid, LogOut, Map } from 'lucide-vue-next'

const router = useRouter()

function logout() {
  localStorage.removeItem('access_token')
  router.push('/login')
}
</script>

<template>
  <div class="flex flex-col min-h-screen" style="background: var(--bg-base)">
    <!-- Top navbar -->
    <header class="flex items-center justify-between px-3 sm:px-6 h-14 shrink-0 gap-2" style="background: var(--bg-card); border-bottom: 1px solid var(--border)">
      <div class="flex items-center gap-2 sm:gap-3 min-w-0">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0" style="background: linear-gradient(135deg, var(--accent), #6366f1)">
          <Map :size="16" color="white" />
        </div>
        <span class="font-bold text-xs sm:text-sm tracking-wide truncate" style="color: var(--text-primary)">КАРТА ПРОСТРАНСТВА</span>
        <span class="badge badge-red text-[10px] sm:text-xs font-medium shrink-0">Studio</span>
      </div>

      <nav class="hidden sm:flex items-center gap-1">
        <RouterLink
          to="/admin/spaces"
          class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
          style="color: var(--text-secondary)"
          active-class="!text-white"
          :style="$route.path.startsWith('/admin/spaces') ? 'color: var(--text-primary); background: var(--bg-surface)' : ''"
        >
          <LayoutGrid :size="15" />
          Пространства
        </RouterLink>
      </nav>

      <button id="admin-logout" @click="logout" class="btn btn-ghost gap-2 text-xs py-1.5 px-3">
        <LogOut :size="14" />
        Выйти
      </button>
    </header>

    <!-- Main content -->
    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>
  </div>
</template>
