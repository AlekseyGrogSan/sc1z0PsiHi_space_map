import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../modules/studio/views/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../modules/studio/views/RegisterView.vue'),
    meta: { public: true },
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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else if (to.meta.public && token) {
    next('/admin')
  } else {
    next()
  }
})

export default router
