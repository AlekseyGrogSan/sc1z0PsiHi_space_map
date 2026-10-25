import apiClient from './client'

export const panoramaApi = {
  getPanorama: (id: string | number) => apiClient.get(`/panoramas/${id}`),

  getUploadUrl: (id: string | number) => apiClient.post(`/panoramas/${id}/upload-ready-url`),

  uploadStitchFrame: (id: string | number, formData: FormData) => apiClient.post(`/panoramas/${id}/stitch-session`, formData),

  createConnection: (data: any) => apiClient.post(`/panoramas/connections`, data),
}

