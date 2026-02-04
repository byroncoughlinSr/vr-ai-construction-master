import { ref, reactive } from 'vue'
import type {
  WebSocketMessage,
  ProjectUpdateMessage,
  TaskUpdateMessage
} from 'src/types/models'

export interface WebSocketConfig {
  url: string
  reconnectInterval: number
  maxReconnectAttempts: number
  heartbeatInterval: number
}

export class WebSocketService {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private heartbeatTimer: number | null = null
  private reconnectTimer: number | null = null

  // Reactive state
  public connected = ref(false)
  public connecting = ref(false)
  public messages = reactive<WebSocketMessage[]>([])
  public lastMessage = ref<WebSocketMessage | null>(null)

  // Event handlers
  private messageHandlers = new Map<string, ((message: WebSocketMessage) => void)[]>()
  private connectionHandlers = new Map<string, (() => void)[]>()

  constructor(private config: Partial<WebSocketConfig> = {}) {
    this.config = {
      url: config.url || import.meta.env.VITE_WS_URL,
      reconnectInterval: config.reconnectInterval || 5000,
      maxReconnectAttempts: config.maxReconnectAttempts || 10,
      heartbeatInterval: config.heartbeatInterval || 30000,
      ...config
    }
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.connected.value || this.connecting.value) {
        resolve()
        return
      }

      this.connecting.value = true

      try {
        this.ws = new WebSocket(this.config.url!)

        this.ws.onopen = () => {
          console.log('WebSocket connected')
          this.connected.value = true
          this.connecting.value = false
          this.reconnectAttempts = 0
          this.startHeartbeat()
          this.emitConnectionEvent('connected')
          resolve()
        }

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data)
            this.handleMessage(message)
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error)
          }
        }

        this.ws.onclose = (event) => {
          console.log('WebSocket disconnected:', event.code, event.reason)
          this.connected.value = false
          this.connecting.value = false
          this.stopHeartbeat()
          this.emitConnectionEvent('disconnected')

          if (!event.wasClean && this.reconnectAttempts < (this.config.maxReconnectAttempts || 10)) {
            this.scheduleReconnect()
          }
        }

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error)
          this.connecting.value = false
          reject(error)
        }

      } catch (error) {
        this.connecting.value = false
        reject(error)
      }
    })
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    this.stopHeartbeat()

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect')
      this.ws = null
    }

    this.connected.value = false
    this.connecting.value = false
  }

  send(data: any): void {
    if (this.ws && this.connected.value) {
      try {
        const message = JSON.stringify(data)
        this.ws.send(message)
      } catch (error) {
        console.error('Failed to send WebSocket message:', error)
      }
    } else {
      console.warn('WebSocket is not connected')
    }
  }

  // Message handling
  private handleMessage(message: WebSocketMessage): void {
    // Store message
    this.messages.push(message)
    this.lastMessage.value = message

    // Keep only last 100 messages
    if (this.messages.length > 100) {
      this.messages.shift()
    }

    // Emit to specific handlers
    this.emitMessageEvent(message.type, message)

    // Handle special message types
    switch (message.type) {
      case 'ping':
        this.handlePing()
        break
      case 'project_update':
        this.handleProjectUpdate(message as ProjectUpdateMessage)
        break
      case 'task_update':
        this.handleTaskUpdate(message as TaskUpdateMessage)
        break
    }
  }

  private handlePing(): void {
    this.send({ type: 'pong', timestamp: new Date().toISOString() })
  }

  private handleProjectUpdate(message: ProjectUpdateMessage): void {
    // Emit project update event
    this.emitMessageEvent('project_update', message)
  }

  private handleTaskUpdate(message: TaskUpdateMessage): void {
    // Emit task update event
    this.emitMessageEvent('task_update', message)
  }

  // Event system
  onMessage(type: string, handler: (message: WebSocketMessage) => void): void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, [])
    }
    this.messageHandlers.get(type)!.push(handler)
  }

  offMessage(type: string, handler?: (message: WebSocketMessage) => void): void {
    if (!this.messageHandlers.has(type)) return

    const handlers = this.messageHandlers.get(type)!
    if (handler) {
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    } else {
      handlers.length = 0
    }
  }

  onConnection(event: string, handler: () => void): void {
    if (!this.connectionHandlers.has(event)) {
      this.connectionHandlers.set(event, [])
    }
    this.connectionHandlers.get(event)!.push(handler)
  }

  offConnection(event: string, handler?: () => void): void {
    if (!this.connectionHandlers.has(event)) return

    const handlers = this.connectionHandlers.get(event)!
    if (handler) {
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    } else {
      handlers.length = 0
    }
  }

  private emitMessageEvent(type: string, message: WebSocketMessage): void {
    const handlers = this.messageHandlers.get(type)
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(message)
        } catch (error) {
          console.error('Error in message handler:', error)
        }
      })
    }
  }

  private emitConnectionEvent(event: string): void {
    const handlers = this.connectionHandlers.get(event)
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler()
        } catch (error) {
          console.error('Error in connection handler:', error)
        }
      })
    }
  }

  // Heartbeat
  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeatTimer = window.setInterval(() => {
      if (this.connected.value) {
        this.send({ type: 'ping', timestamp: new Date().toISOString() })
      }
    }, this.config.heartbeatInterval)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  // Reconnection
  private scheduleReconnect(): void {
    this.reconnectAttempts++
    const delay = Math.min(
      (this.config.reconnectInterval || 5000) * Math.pow(2, this.reconnectAttempts - 1),
      30000
    )

    console.log(`Scheduling reconnect attempt ${this.reconnectAttempts} in ${delay}ms`)

    this.reconnectTimer = window.setTimeout(() => {
      this.connect().catch(error => {
        console.error('Reconnection failed:', error)
      })
    }, delay)
  }

  // Utility methods
  getConnectionState(): 'disconnected' | 'connecting' | 'connected' {
    if (this.connected.value) return 'connected'
    if (this.connecting.value) return 'connecting'
    return 'disconnected'
  }

  getMessageHistory(type?: string, limit = 50): WebSocketMessage[] {
    let messages = this.messages
    if (type) {
      messages = messages.filter(msg => msg.type === type)
    }
    return messages.slice(-limit)
  }

  clearMessageHistory(): void {
    this.messages.length = 0
    this.lastMessage.value = null
  }

  // Project-specific methods
  subscribeToProject(projectId: number): void {
    this.send({
      type: 'subscribe',
      data: { project_id: projectId }
    })
  }

  unsubscribeFromProject(projectId: number): void {
    this.send({
      type: 'unsubscribe',
      data: { project_id: projectId }
    })
  }

  // Cleanup
  destroy(): void {
    this.disconnect()
    this.messageHandlers.clear()
    this.connectionHandlers.clear()
    this.clearMessageHistory()
  }
}

// Create and export default instance
export const websocketService = new WebSocketService()

// Export types
export type { WebSocketMessage, ProjectUpdateMessage, TaskUpdateMessage }
