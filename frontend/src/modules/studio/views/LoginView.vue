<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '../../../api'
import { LogIn, Eye, EyeOff } from 'lucide-vue-next'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')
const showPwd = ref(false)

async function handleLogin() {
  if (!form.username || !form.password) return
  loading.value = true
  error.value = ''
  try {
    const { data } = await authApi.login({username: form.username, password: form.password})
    localStorage.setItem('access_token', data.access_token)
    router.push('/admin/spaces')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Неверный логин или пароль'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center px-4" style="background: radial-gradient(ellipse at 60% 0%, rgba(59,130,246,0.08) 0%, transparent 60%), var(--bg-base)">
    <!-- Logo / Brand -->
    <div class="w-full max-w-md fade-in">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4" style="background: linear-gradient(135deg, var(--accent), #6366f1)">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
        </div>
        <h1 class="text-2xl font-bold" style="color: var(--text-primary)">Карта Пространства</h1>
        <p class="text-sm mt-1" style="color: var(--text-muted)">Панель организатора</p>
      </div>

      <!-- Card -->
      <div class="card p-8">
        <h2 class="text-lg font-semibold mb-6" style="color: var(--text-primary)">Вход в аккаунт</h2>

        <form @submit.prevent="handleLogin" class="space-y-4">
          <div>
            <label class="label">Логин / Email</label>
            <input
              id="login-username"
              v-model="form.username"
              type="text"
              class="input"
              placeholder="organizer@example.com"
              autocomplete="username"
              required
            />
          </div>

          <div>
            <label class="label">Пароль</label>
            <div class="relative">
              <input
                id="login-password"
                v-model="form.password"
                :type="showPwd ? 'text' : 'password'"
                class="input pr-10"
                placeholder="••••••••"
                autocomplete="current-password"
                required
              />
              <button
                type="button"
                class="absolute right-3 top-1/2 -translate-y-1/2 transition-colors"
                style="color: var(--text-muted)"
                @click="showPwd = !showPwd"
              >
                <Eye v-if="!showPwd" :size="16" />
                <EyeOff v-else :size="16" />
              </button>
            </div>
          </div>

          <!-- Error -->
          <div v-if="error" class="flex items-center gap-2 p-3 rounded-lg text-sm" style="background: rgba(239,68,68,0.1); color: #f87171; border: 1px solid rgba(239,68,68,0.2)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ error }}
          </div>

          <button id="login-submit" type="submit" :disabled="loading" class="btn btn-primary w-full justify-center py-2.5 text-sm font-semibold mt-2">
            <span v-if="loading" class="spinner w-4 h-4"></span>
            <LogIn v-else :size="16" />
            {{ loading ? 'Вход...' : 'Войти' }}
          </button>
        </form>

        <p class="text-center text-sm mt-6" style="color: var(--text-muted)">
          Нет аккаунта?
          <RouterLink to="/register" class="font-medium transition-colors" style="color: var(--accent)">Зарегистрироваться</RouterLink>
        </p>
      </div>

      <!-- Footer -->
      <p class="text-center text-xs mt-6" style="color: var(--text-muted)">
        ТТК Хакатон 2026 · Indoor Navigation Platform
      </p>
    </div>
  </div>
</template>
