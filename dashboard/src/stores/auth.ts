import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { User, AuthTokens } from 'src/types/models'

interface AuthState {
  user: User | null
  token: string | null
  refreshToken: string | null
  loading: boolean
  error: string | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    token: localStorage.getItem('auth_token'),
    refreshToken: localStorage.getItem('refresh_token'),
    loading: false,
    error: null
  }),

  getters: {
    isAuthenticated: (state): boolean => !!state.token && !!state.user,
    isAdmin: (state): boolean => state.user?.role === 'admin',
    isManager: (state): boolean => state.user?.role === 'manager',
    isWorker: (state): boolean => state.user?.role === 'worker',
    isClient: (state): boolean => state.user?.role === 'client',

    hasPermission: (state) => (permission: string): boolean =>
      state.user?.permissions?.includes(permission) || false,

    hasAnyPermission: (state) => (permissions: string[]): boolean =>
      permissions.some(permission => state.user?.permissions?.includes(permission)) || false,

    hasAllPermissions: (state) => (permissions: string[]): boolean =>
      permissions.every(permission => state.user?.permissions?.includes(permission)) || false,

    canManageProjects: (state): boolean =>
      state.user?.role === 'admin' || state.user?.role === 'manager',

    canViewAllProjects: (state): boolean =>
      state.user?.role === 'admin' || state.user?.role === 'manager',

    canEditMaterials: (state): boolean =>
      state.user?.role === 'admin' || state.user?.role === 'manager' || state.user?.role === 'worker',

    canViewReports: (state): boolean =>
      state.user?.role === 'admin' || state.user?.role === 'manager' || state.user?.role === 'client',

    fullName: (state): string => {
      if (!state.user) return ''
      return `${state.user.first_name} ${state.user.last_name}`.trim()
    },

    userInitials: (state): string => {
      if (!state.user) return ''
      return `${state.user.first_name.charAt(0)}${state.user.last_name.charAt(0)}`.toUpperCase()
    }
  },

  actions: {
    async login(credentials: { username: string; password: string }): Promise<{ user: User; tokens: AuthTokens }> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.post<{ user: User; tokens: AuthTokens }>('/auth/login', credentials)

        this.user = response.user
        this.token = response.tokens.access_token
        this.refreshToken = response.tokens.refresh_token

        // Store tokens
        if (this.token) localStorage.setItem('auth_token', this.token)
        if (this.refreshToken) localStorage.setItem('refresh_token', this.refreshToken)

        // Set authorization header
        if (this.token) {
          apiClient.client.defaults.headers.common['Authorization'] = `Bearer ${this.token}`
        }

        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Login failed:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async logout(): Promise<void> {
      this.loading = true
      try {
        if (this.token) {
          await apiClient.post('/auth/logout', {})
        }
      } catch (error) {
        // Ignore logout errors
        console.warn('Logout request failed:', error)
      } finally {
        // Clear local state regardless of API response
        this.clearAuthData()
        this.loading = false
      }
    },

    async refreshAuthToken(): Promise<void> {
      if (!this.refreshToken) {
        throw new Error('No refresh token available')
      }

      try {
        const response = await apiClient.post<{ access_token: string; refresh_token?: string }>('/auth/refresh', {
          refresh_token: this.refreshToken
        })

        this.token = response.access_token
        if (response.refresh_token) {
          this.refreshToken = response.refresh_token
          localStorage.setItem('refresh_token', this.refreshToken)
        }

        localStorage.setItem('auth_token', this.token)
        apiClient.client.defaults.headers.common['Authorization'] = `Bearer ${this.token}`

      } catch (error) {
        console.error('Token refresh failed:', error)
        this.clearAuthData()
        throw error
      }
    },

    async register(userData: {
      username: string
      email: string
      password: string
      first_name: string
      last_name: string
      role?: User['role']
    }): Promise<{ user: User; tokens: AuthTokens }> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.post<{ user: User; tokens: AuthTokens }>('/auth/register', userData)

        this.user = response.user
        this.token = response.tokens.access_token
        this.refreshToken = response.tokens.refresh_token

        localStorage.setItem('auth_token', this.token)
        localStorage.setItem('refresh_token', this.refreshToken)

        if (this.token) {
          apiClient.client.defaults.headers.common['Authorization'] = `Bearer ${this.token}`
        }

        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Registration failed:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async updateProfile(userData: Partial<User>): Promise<User> {
      this.loading = true
      this.error = null
      try {
        const response = await apiClient.put<User>('/auth/profile', userData)
        this.user = response
        return response
      } catch (error) {
        this.error = (error as Error).message
        console.error('Profile update failed:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async changePassword(passwords: { current_password: string; new_password: string }): Promise<void> {
      this.loading = true
      this.error = null
      try {
        await apiClient.post('/auth/change-password', passwords)
      } catch (error) {
        this.error = (error as Error).message
        console.error('Password change failed:', error)
        throw error
      } finally {
        this.loading = false
      }
    },

    async requestPasswordReset(email: string): Promise<void> {
      try {
        await apiClient.post('/auth/forgot-password', { email })
      } catch (error) {
        console.error('Password reset request failed:', error)
        throw error
      }
    },

    async resetPassword(token: string, newPassword: string): Promise<void> {
      try {
        await apiClient.post('/auth/reset-password', { token, password: newPassword })
      } catch (error) {
        console.error('Password reset failed:', error)
        throw error
      }
    },

    // Token validation
    async validateToken(): Promise<boolean> {
      if (!this.token) return false

      try {
        const response = await apiClient.post<{ valid: boolean }>('/auth/validate', {})
        return response.valid
      } catch (error) {
        console.warn('Token validation failed:', error)
        return false
      }
    },

    // Session management
    async initializeAuth(): Promise<void> {
      if (this.token && !this.user) {
        try {
          // Try to get current user info
          this.user = await apiClient.get<User>('/auth/me')
        } catch (error) {
          console.warn('Failed to get user info:', error)
          this.clearAuthData()
        }
      }
    },

    async checkSession(): Promise<boolean> {
      if (!this.token) return false

      const isValid = await this.validateToken()
      if (!isValid) {
        try {
          await this.refreshAuthToken()
          return true
        } catch (error) {
          this.clearAuthData()
          return false
        }
      }

      return true
    },

    // Utility methods
    clearAuthData(): void {
      this.user = null
      this.token = null
      this.refreshToken = null
      this.error = null

      localStorage.removeItem('auth_token')
      localStorage.removeItem('refresh_token')
      delete apiClient.client.defaults.headers.common['Authorization']
    },

    setAuthData(user: User, tokens: AuthTokens): void {
      this.user = user
      this.token = tokens.access_token
      this.refreshToken = tokens.refresh_token

      localStorage.setItem('auth_token', this.token)
      localStorage.setItem('refresh_token', this.refreshToken)

      if (this.token) {
        apiClient.client.defaults.headers.common['Authorization'] = `Bearer ${this.token}`
      }
    },

    clearError(): void {
      this.error = null
    }
  }
})
