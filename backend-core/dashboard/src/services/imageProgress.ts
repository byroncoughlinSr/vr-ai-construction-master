/**
 * Image Progress WebSocket Service
 * 
 * Manages WebSocket connections for real-time image generation progress tracking.
 * Connects to backend WebSocket endpoint to receive step-by-step updates during
 * AI image generation.
 */

export interface ImageProgress {
  generation_id: string;
  step: number;
  total_steps: number;
  percentage: number;
  status: 'generating' | 'completed' | 'failed';
}

export interface ImageGenerationResult {
  success: boolean;
  images: Array<{
    image_data: string;
    image_url: string;
    filename: string;
  }>;
  count: number;
  metadata: {
    prompt: string;
    width: number;
    height: number;
    steps: number;
    guidance_scale: number;
    model: string;
  };
}

export class ImageProgressService {
  private ws: WebSocket | null = null;
  private callbacks: Map<string, (progress: ImageProgress) => void> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private reconnectDelay = 1000; // 1 second

  /**
   * Connect to WebSocket for a specific generation
   * @param generationId - Unique ID for the image generation
   * @param onProgress - Callback function for progress updates
   * @param wsBaseUrl - Base WebSocket URL (default: ws://localhost:8000)
   */
  connect(
    generationId: string,
    onProgress: (progress: ImageProgress) => void,
    wsBaseUrl: string = 'ws://localhost:8000'
  ): void {
    const wsUrl = `${wsBaseUrl}/api/v1/ws/image-progress/${generationId}`;

    console.log(`[ImageProgress] Connecting to ${wsUrl}`);

    try {
      this.ws = new WebSocket(wsUrl);
      this.callbacks.set(generationId, onProgress);

      this.ws.onopen = () => {
        console.log(`[ImageProgress] Connected for generation ${generationId}`);
        this.reconnectAttempts = 0; // Reset reconnect counter on success
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('[ImageProgress] Received:', data);

          this.handleMessage(data, generationId, onProgress);
        } catch (error) {
          console.error('[ImageProgress] Failed to parse message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[ImageProgress] WebSocket error:', error);
      };

      this.ws.onclose = (event) => {
        console.log(`[ImageProgress] WebSocket closed (code: ${event.code})`);
        this.callbacks.delete(generationId);

        // Attempt reconnection if not a normal closure
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          console.log(`[ImageProgress] Reconnecting (attempt ${this.reconnectAttempts})...`);
          setTimeout(() => {
            this.connect(generationId, onProgress, wsBaseUrl);
          }, this.reconnectDelay * this.reconnectAttempts);
        }
      };
    } catch (error) {
      console.error('[ImageProgress] Failed to create WebSocket:', error);
      throw error;
    }
  }

  /**
   * Handle incoming WebSocket messages
   */
  private handleMessage(
    data: any,
    generationId: string,
    onProgress: (progress: ImageProgress) => void
  ): void {
    switch (data.type) {
      case 'progress':
        onProgress({
          generation_id: data.generation_id,
          step: data.step,
          total_steps: data.total_steps,
          percentage: data.percentage,
          status: 'generating'
        });
        break;

      case 'completed':
        onProgress({
          generation_id: data.generation_id,
          step: data.result?.metadata?.steps || 0,
          total_steps: data.result?.metadata?.steps || 0,
          percentage: 100,
          status: 'completed'
        });
        // Auto-disconnect on completion
        setTimeout(() => this.disconnect(), 500);
        break;

      case 'error':
        onProgress({
          generation_id: data.generation_id,
          step: 0,
          total_steps: 0,
          percentage: 0,
          status: 'failed'
        });
        // Auto-disconnect on error
        setTimeout(() => this.disconnect(), 500);
        break;

      case 'ping':
        // Respond to server ping with pong
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({ type: 'pong' }));
        }
        break;

      default:
        console.warn('[ImageProgress] Unknown message type:', data.type);
    }
  }

  /**
   * Disconnect from WebSocket
   */
  disconnect(): void {
    if (this.ws) {
      console.log('[ImageProgress] Disconnecting...');
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
      this.callbacks.clear();
    }
  }

  /**
   * Check if WebSocket is connected
   */
  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  /**
   * Send ping to keep connection alive
   */
  ping(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }
}

/**
 * Create a singleton instance for app-wide use
 */
export const imageProgressService = new ImageProgressService();
