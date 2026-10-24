<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { authApi } from '../../../api'
import { UserPlus, Eye, EyeOff } from 'lucide-vue-next'

const router = useRouter()
const form = reactive({ username: '', email: '', password: '', confirm: '' })
const loading = ref(false)
const error = ref('')
const showPwd = ref(false)

async function handleRegister() {
  if (form.password !== form.confirm) {
    error.value = 'Пароли не совпадают'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await authApi.register({ username: form.username, email: form.email, password: form.password })
    // Auto-login
    const params = new URLSearchParams()
    params.append('username', form.username)
    params.append('password', form.password)
    const { data } = await authApi.login(params)
    localStorage.setItem('access_token', data.access_token)
    router.push('/admin/spaces')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Ошибка регистрации'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center px-4" style="background: radial-gradient(ellipse at 40% 0%, rgba(59,130,246,0.08) 0%, transparent 60%), var(--bg-base)">
    <div class="w-full max-w-md fade-in">
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl mb-4" style="background: linear-gradient(135deg, var(--accent), #6366f1)">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
        </div>
        <h1 class="text-2xl font-bold" style="color: var(--text-primary)">Карта Пространства</h1>
        <p class="text-sm mt-1" style="color: var(--text-muted)">Создайте аккаунт организатора</p>
      </div>

      <div class="card p-8">
        <h2 class="text-lg font-semibold mb-6" style="color: var(--text-primary)">Регистрация</h2>

        <form @submit.prevent="handleRegister" class="space-y-4">
          <div>
            <label class="label">Имя пользователя</label>
            <input id="reg-username" v-model="form.username" type="text" class="input" placeholder="organizer2026" required />
          </div>
          <div>
            <label class="label">Email</label>
            <input id="reg-email" v-model="form.email" type="email" class="input" placeholder="you@example.com" required />
          </div>
          <div>
            <label class="label">Пароль</label>
            <div class="relative">
              <input id="reg-password" v-model="form.password" :type="showPwd ? 'text' : 'password'" class="input pr-10" placeholder="••••••••" required minlength="6" />
              <button type="button" class="absolute right-3 top-1/2 -translate-y-1/2" style="color: var(--text-muted)" @click="showPwd = !showPwd">
                <Eye v-if="!showPwd" :size="16" /><EyeOff v-else :size="16" />
              </button>
            </div>
          </div>
          <div>
            <label class="label">Подтвердите пароль</label>
            <input id="reg-confirm" v-model="form.confirm" :type="showPwd ? 'text' : 'password'" class="input" placeholder="••••••••" required />
          </div>

          <div v-if="error" class="flex items-center gap-2 p-3 rounded-lg text-sm" style="background: rgba(239,68,68,0.1); color: #f87171; border: 1px solid rgba(239,68,68,0.2)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ error }}
          </div>

          <button id="reg-submit" type="submit" :disabled="loading" class="btn btn-primary w-full justify-center py-2.5 text-sm font-semibold mt-2">
            <span v-if="loading" class="spinner w-4 h-4"></span>
            <UserPlus v-else :size="16" />
            {{ loading ? 'Создание...' : 'Создать аккаунт' }}
          </button>
        </form>

        <p class="text-center text-sm mt-6" style="color: var(--text-muted)">
          Уже есть аккаунт?
          <RouterLink to="/login" class="font-medium transition-colors" style="color: var(--accent)">Войти</RouterLink>
        </p>
      </div>
    </div>
  </div>
</template>
