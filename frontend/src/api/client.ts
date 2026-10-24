import axios, { type AxiosInstance, type AxiosError } from 'axios'

export const apiClient: AxiosInstance = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
  timeout: 8000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
})

// Перехватчик ответов и логирование/обработка ошибок
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const status = error.response?.status
    const url = error.config?.url
    const message = (error.response?.data as { detail?: string })?.detail || error.message || 'Ошибка сети'

    console.warn(`[API Error ${status || 'TIMEOUT/NETWORK'}] ${url}: ${message}`)
    return Promise.reject(error)
  }
)

export default apiClient
