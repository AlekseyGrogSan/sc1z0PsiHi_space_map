import axios, { 
  type AxiosInstance, 
  type InternalAxiosRequestConfig, 
  type AxiosResponse, 
  type AxiosError 
} from 'axios'

function resolveBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_URL

  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location
    // Если фронтенд открыт по внешнему IP или домену (не localhost) —
    // автоматически направляем запросы на бэкенд того же хоста (порт 8000)
    if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
      if (!envUrl || envUrl.includes('localhost') || envUrl.includes('127.0.0.1')) {
        return `${protocol}//${hostname}:8000/api/v1`
      }
    }
  }

  return envUrl || 'http://localhost:8000/api/v1'
}

const BASE_URL = resolveBaseUrl()

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

// Перехватчик запросов: добавление JWT токена
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('access_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Перехватчик ответов: логирование и обработка 401 (редирект на логин только для защищенных роутов)
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const status = error.response?.status
    const url = error.config?.url
    const message = (error.response?.data as { detail?: string })?.detail || error.message || 'Ошибка сети'

    console.warn(`[API Error ${status || 'TIMEOUT/NETWORK'}] ${url}: ${message}`)
    
    if (status === 401) {
      // Не делаем перезагрузку/редирект, если ошибка возникла при логине/регистрации
      const isAuthRequest = url?.includes('/auth/login') || url?.includes('/auth/register')
      const isAuthPage = window.location.pathname === '/login' || window.location.pathname === '/register'
      
      if (!isAuthRequest && !isAuthPage) {
        localStorage.removeItem('access_token')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export { apiClient }
export default apiClient