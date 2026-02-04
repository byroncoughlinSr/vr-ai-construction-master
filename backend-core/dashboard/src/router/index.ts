import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('../views/HomeView.vue')
        },
        {
          path: '/timeline',
          name: 'timeline',
          component: () => import('../views/TimelineView.vue')
        },
        {
          path: '/materials',
          name: 'materials',
          component: () => import('../views/MaterialsView.vue')
        },
        {
          path: '/budget',
          name: 'budget',
          component: () => import('../views/BudgetView.vue')
        },
        {
          path: '/resources',
          name: 'resources',
          component: () => import('../views/ResourcesView.vue')
        },
        {
          path: '/compliance',
          name: 'compliance',
          component: () => import('../views/ComplianceView.vue')
        }
      ]
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue')
    }
  ]
})

export default router
