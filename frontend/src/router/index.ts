import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import SpaceView from '../modules/viewer/views/SpaceView.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/space/ttk-conf-2026',
  },
  {
    path: '/space/:slug',
    name: 'SpaceView',
    component: SpaceView,
    props: true,
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/space/ttk-conf-2026',
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
