import axios from 'axios'

const api = axios.create({
  baseURL: 'http://localhost:8000/api/v1',
})

export const panoramaApi = {
  getPanorama: (id: string | number) => api.get(`/panoramas/${id}`),

  getUploadUrl: (id: string | number) => api.post(`/panoramas/${id}/upload-ready-url`),

  uploadStitchFrame: (id: string | number, formData: FormData) => api.post(`/panoramas/${id}/stitch-session`, formData),

  createConnection: (data: any) => api.post(`/panoramas/connections`, data),
}
