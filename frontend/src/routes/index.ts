import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../modules/studio/views/LoginView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../modules/studio/views/RegisterView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/space/:slug',
    name: 'SpaceView',
    component: () => import('../modules/viewer/views/SpaceView.vue'),
    props: true,
  },
  {
    path: '/tour360',
    name: 'PanoramaViewer',
    component: () => import('../modules/tour360/PanoramaViewer.vue'),
  },
  {
    path: '/camera-assistant',
    name: 'CameraAssistant',
    component: () => import('../modules/tour360/CameraAssistant.vue'),
  },
  {
    path: '/admin',
    component: () => import('../modules/studio/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/admin/spaces',
      },
      {
        path: 'spaces',
        name: 'Spaces',
        component: () => import('../modules/studio/views/SpacesView.vue'),
      },
      {
        path: 'spaces/:spaceId/floors/:floorId/editor',
        name: 'FloorEditor',
        component: () => import('../modules/studio/views/FloorEditorView.vue'),
        props: true,
      },
    ],
  },
  {
    path: '/',
    redirect: '/admin',
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/admin',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else if (to.meta.guestOnly && token) {
    next('/admin')
  } else {
    next()
  }
})

export default router
