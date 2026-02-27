import axios, { AxiosInstance, AxiosResponse } from 'axios'
import type { ApiResponse, PaginatedResponse } from 'src/types/models'

export interface ApiClientConfig {
  baseURL: string
  timeout: number
  headers: Record<string, string>
}

export class ApiClient {
  public client: AxiosInstance

  constructor(config: Partial<ApiClientConfig> = {}) {
    this.client = axios.create({
      baseURL: config.baseURL || import.meta.env.VITE_API_BASE_URL,
      timeout: config.timeout || 900000, // 15 minutes timeout for long-running operations like image generation
      headers: {
        'Content-Type': 'application/json',
        ...config.headers
      }
    })

    this.setupInterceptors()
  }

  private setupInterceptors(): void {
    // Request interceptor for authentication
    this.client.interceptors.request.use(
      (config) => {
        console.log('[API] Request:', config.method?.toUpperCase(), config.url)
        const token = localStorage.getItem('auth_token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => {
        console.error('[API] Request error:', error)
        return Promise.reject(error)
      }
    )

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => {
        console.log('[API] Response:', response.status, response.config.url, response.data)
        return response
      },
      (error) => {
        console.error('[API] Response error:', {
          url: error.config?.url,
          status: error.response?.status,
          message: error.message,
          data: error.response?.data
        })
        
        if (error.response?.status === 401) {
          // Handle unauthorized access
          localStorage.removeItem('auth_token')
          localStorage.removeItem('refresh_token')
          // Only redirect to login if we're not already there
          if (window.location.pathname !== '/login') {
            window.location.href = '/login'
          }
        }
        return Promise.reject(error)
      }
    )
  }

  // Generic CRUD methods
  async get<T>(endpoint: string, params?: Record<string, any>): Promise<T> {
    const response: AxiosResponse<T> = await this.client.get(endpoint, { params })
    return response.data
  }

  async post<T>(endpoint: string, data: any): Promise<T> {
    const response: AxiosResponse<T> = await this.client.post(endpoint, data)
    return response.data
  }

  async put<T>(endpoint: string, data: any): Promise<T> {
    const response: AxiosResponse<T> = await this.client.put(endpoint, data)
    return response.data
  }

  async patch<T>(endpoint: string, data: any): Promise<T> {
    const response: AxiosResponse<T> = await this.client.patch(endpoint, data)
    return response.data
  }

  async delete<T>(endpoint: string): Promise<T> {
    const response: AxiosResponse<T> = await this.client.delete(endpoint)
    return response.data
  }

  // File upload method
  async uploadFile(endpoint: string, file: File, additionalData?: Record<string, any>): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)

    if (additionalData) {
      Object.keys(additionalData).forEach(key => {
        formData.append(key, additionalData[key])
      })
    }

    const response = await this.client.post(endpoint, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })

    return response.data.data
  }

  // Paginated requests
  async getPaginated<T>(
    endpoint: string,
    page = 1,
    pageSize = 20,
    params?: Record<string, any>
  ): Promise<PaginatedResponse<T>> {
    const response: AxiosResponse<PaginatedResponse<T>> = await this.client.get(endpoint, {
      params: {
        page,
        page_size: pageSize,
        ...params
      }
    })
    return response.data
  }

  // Search method
  async search<T>(
    endpoint: string,
    query: string,
    filters?: Record<string, any>
  ): Promise<T[]> {
    const response: AxiosResponse<T[]> = await this.client.get(endpoint, {
      params: {
        q: query,
        ...filters
      }
    })
    return response.data
  }

  // Batch operations
  async batchGet<T>(endpoints: string[]): Promise<T[]> {
    const promises = endpoints.map(endpoint => this.get<T>(endpoint))
    return Promise.all(promises)
  }

  async batchPost<T>(requests: Array<{ endpoint: string; data: any }>): Promise<T[]> {
    const promises = requests.map(({ endpoint, data }) => this.post<T>(endpoint, data))
    return Promise.all(promises)
  }

  // Cache management
  private cache = new Map<string, { data: any; timestamp: number; ttl: number }>()

  async getCached<T>(
    endpoint: string,
    ttl = 5 * 60 * 1000, // 5 minutes default
    params?: Record<string, any>
  ): Promise<T> {
    const cacheKey = `${endpoint}${JSON.stringify(params)}`
    const cached = this.cache.get(cacheKey)

    if (cached && Date.now() - cached.timestamp < cached.ttl) {
      return cached.data
    }

    const data = await this.get<T>(endpoint, params)
    this.cache.set(cacheKey, { data, timestamp: Date.now(), ttl })
    return data
  }

  clearCache(): void {
    this.cache.clear()
  }

  removeFromCache(endpoint: string, params?: Record<string, any>): void {
    const cacheKey = `${endpoint}${JSON.stringify(params)}`
    this.cache.delete(cacheKey)
  }
}

// Create and export default instance
export const apiClient = new ApiClient()

// Export axios instance for advanced usage
export { axios }
