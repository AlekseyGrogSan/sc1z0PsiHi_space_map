import axios, { 
  type AxiosInstance, 
  type InternalAxiosRequestConfig, 
  type AxiosResponse, 
  type AxiosError 
} from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 8000,
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

// Перехватчик ответов: логирование и обработка 401 (редирект на логин)
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const status = error.response?.status
    const url = error.config?.url
    const message = (error.response?.data as { detail?: string })?.detail || error.message || 'Ошибка сети'

    console.warn(`[API Error ${status || 'TIMEOUT/NETWORK'}] ${url}: ${message}`)
    
    if (status === 401) {
      localStorage.removeItem('access_token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default apiClient