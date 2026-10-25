import apiClient from './client'

export const panoramaApi = {
  getPanorama: (id: string | number) => apiClient.get(`/panoramas/${id}`),

  listByFloor: (floorId: string | number) => apiClient.get(`/floors/${floorId}/panoramas`),

  upload: (floorId: string | number, formData: FormData) =>
    apiClient.post(`/floors/${floorId}/panoramas/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),

  getUploadUrl: (id: string | number) => apiClient.post(`/panoramas/${id}/upload-ready-url`),

  uploadStitchFrame: (id: string | number, formData: FormData) => apiClient.post(`/panoramas/${id}/stitch-session`, formData),

  createConnection: (data: any) => apiClient.post(`/panoramas/connections`, data),

  delete: (id: string | number) => apiClient.delete(`/panoramas/${id}`),
}


