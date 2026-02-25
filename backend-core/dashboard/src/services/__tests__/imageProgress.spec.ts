/**
 * Tests for Image Progress WebSocket Service
 * 
 * Tests the WebSocket service that manages real-time progress tracking
 * for AI image generation.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { ImageProgressService, type ImageProgress } from '../imageProgress';

describe('ImageProgressService', () => {
  let service: ImageProgressService;
  let mockWebSocket: any;
  let originalWebSocket: any;

  beforeEach(() => {
    // Save original WebSocket
    originalWebSocket = global.WebSocket;

    // Create mock WebSocket
    mockWebSocket = {
      readyState: WebSocket.OPEN,
      send: vi.fn(),
      close: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      onopen: null,
      onmessage: null,
      onerror: null,
      onclose: null
    };

    // Mock WebSocket constructor (with required static constants)
    global.WebSocket = vi.fn(() => mockWebSocket) as any;
    (global.WebSocket as any).CONNECTING = 0;
    (global.WebSocket as any).OPEN = 1;
    (global.WebSocket as any).CLOSING = 2;
    (global.WebSocket as any).CLOSED = 3;

    service = new ImageProgressService();
  });

  afterEach(() => {
    // Restore original WebSocket
    global.WebSocket = originalWebSocket;
    service.disconnect();
  });

  describe('connect', () => {
    it('should create WebSocket connection with correct URL', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);

      expect(global.WebSocket).toHaveBeenCalledWith(
        `ws://localhost:8000/api/v1/ws/image-progress/${generationId}`
      );
    });

    it('should accept custom WebSocket base URL', () => {
      const generationId = 'test-123';
      const callback = vi.fn();
      const customUrl = 'ws://custom-server:9000';

      service.connect(generationId, callback, customUrl);

      expect(global.WebSocket).toHaveBeenCalledWith(
        `${customUrl}/api/v1/ws/image-progress/${generationId}`
      );
    });

    it('should handle progress messages', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);

      // Simulate progress message
      const progressData = {
        type: 'progress',
        generation_id: generationId,
        step: 25,
        total_steps: 50,
        percentage: 50,
        status: 'generating'
      };

      mockWebSocket.onmessage({
        data: JSON.stringify(progressData)
      });

      expect(callback).toHaveBeenCalledWith({
        generation_id: generationId,
        step: 25,
        total_steps: 50,
        percentage: 50,
        status: 'generating'
      });
    });

    it('should handle completion messages', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);

      const completionData = {
        type: 'completed',
        generation_id: generationId,
        result: {
          metadata: {
            steps: 50
          }
        }
      };

      mockWebSocket.onmessage({
        data: JSON.stringify(completionData)
      });

      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({
          generation_id: generationId,
          status: 'completed',
          percentage: 100
        })
      );
    });

    it('should handle error messages', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);

      const errorData = {
        type: 'error',
        generation_id: generationId,
        error: 'Generation failed'
      };

      mockWebSocket.onmessage({
        data: JSON.stringify(errorData)
      });

      expect(callback).toHaveBeenCalledWith({
        generation_id: generationId,
        step: 0,
        total_steps: 0,
        percentage: 0,
        status: 'failed'
      });
    });

    it('should respond to ping messages with pong', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);

      mockWebSocket.onmessage({
        data: JSON.stringify({ type: 'ping' })
      });

      expect(mockWebSocket.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'pong' })
      );
    });

    it('should handle malformed JSON gracefully', () => {
      const generationId = 'test-123';
      const callback = vi.fn();
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

      service.connect(generationId, callback);

      mockWebSocket.onmessage({
        data: 'invalid json{'
      });

      expect(callback).not.toHaveBeenCalled();
      expect(consoleError).toHaveBeenCalled();

      consoleError.mockRestore();
    });
  });

  describe('disconnect', () => {
    it('should close WebSocket connection', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);
      service.disconnect();

      expect(mockWebSocket.close).toHaveBeenCalledWith(1000, 'Client disconnect');
    });

    it('should clear callbacks', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);
      service.disconnect();

      // Attempting to send message after disconnect should not crash
      expect(() => {
        mockWebSocket.onmessage({
          data: JSON.stringify({ type: 'progress', step: 1 })
        });
      }).not.toThrow();
    });

    it('should handle disconnect when not connected', () => {
      expect(() => {
        service.disconnect();
      }).not.toThrow();
    });
  });

  describe('isConnected', () => {
    it('should return true when WebSocket is open', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);
      mockWebSocket.readyState = WebSocket.OPEN;

      expect(service.isConnected()).toBe(true);
    });

    it('should return false when not connected', () => {
      expect(service.isConnected()).toBe(false);
    });

    it('should return false when WebSocket is closed', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);
      mockWebSocket.readyState = WebSocket.CLOSED;

      expect(service.isConnected()).toBe(false);
    });
  });

  describe('ping', () => {
    it('should send ping when connected', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);
      mockWebSocket.readyState = WebSocket.OPEN;

      service.ping();

      expect(mockWebSocket.send).toHaveBeenCalledWith(
        JSON.stringify({ type: 'ping' })
      );
    });

    it('should not send ping when not connected', () => {
      service.ping();

      expect(mockWebSocket.send).not.toHaveBeenCalled();
    });
  });

  describe('reconnection', () => {
    it('should attempt to reconnect on abnormal closure', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      // Use fake timers for testing reconnection
      vi.useFakeTimers();

      service.connect(generationId, callback);

      // Simulate abnormal closure
      mockWebSocket.onclose({ code: 1006 });

      // Fast-forward time to trigger reconnection
      vi.advanceTimersByTime(1000);

      // WebSocket constructor should be called again
      expect(global.WebSocket).toHaveBeenCalledTimes(2);

      vi.useRealTimers();
    });

    it('should not reconnect on normal closure', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      service.connect(generationId, callback);

      // Simulate normal closure
      mockWebSocket.onclose({ code: 1000 });

      // Should not attempt reconnection
      expect(global.WebSocket).toHaveBeenCalledTimes(1);
    });

    it('should limit reconnection attempts', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      vi.useFakeTimers();

      service.connect(generationId, callback);

      // Simulate multiple abnormal closures
      for (let i = 0; i < 5; i++) {
        mockWebSocket.onclose({ code: 1006 });
        vi.advanceTimersByTime(1000 * (i + 1));
      }

      // Should only reconnect up to max attempts (3)
      // Initial connection + 3 reconnections = 4 total
      expect(global.WebSocket).toHaveBeenCalledTimes(4);

      vi.useRealTimers();
    });
  });

  describe('auto-disconnect', () => {
    it('should auto-disconnect after completion', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      vi.useFakeTimers();

      service.connect(generationId, callback);

      const completionData = {
        type: 'completed',
        generation_id: generationId,
        result: { metadata: { steps: 50 } }
      };

      mockWebSocket.onmessage({
        data: JSON.stringify(completionData)
      });

      // Fast-forward time past the disconnect delay
      vi.advanceTimersByTime(600);

      expect(mockWebSocket.close).toHaveBeenCalled();

      vi.useRealTimers();
    });

    it('should auto-disconnect after error', () => {
      const generationId = 'test-123';
      const callback = vi.fn();

      vi.useFakeTimers();

      service.connect(generationId, callback);

      const errorData = {
        type: 'error',
        generation_id: generationId,
        error: 'Test error'
      };

      mockWebSocket.onmessage({
        data: JSON.stringify(errorData)
      });

      vi.advanceTimersByTime(600);

      expect(mockWebSocket.close).toHaveBeenCalled();

      vi.useRealTimers();
    });
  });
});
