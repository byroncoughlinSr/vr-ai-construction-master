import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import { errorMessage } from 'src/utils/errors'

// What the copilot may offer to do (ai_assistant_service.clean_actions). The
// widget asks before running one.
export type CopilotAction =
  | { type: 'refine_floor_plan'; label: string; instruction: string }
  | { type: 'create_task'; label: string; phase_id: number; name: string; priority: string; duration_days: number }
  | { type: 'draft_email'; label: string; client_id: number; purpose: string }
  | { type: 'create_change_order'; label: string; title: string; description: string; cost_impact: number }
  | { type: 'navigate'; label: string; route: string }

export interface CopilotMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  actions?: CopilotAction[]
  source?: string
  error?: boolean
  done?: string[] // labels of actions already run
}

export const COPILOT_SUGGESTIONS = [
  'What needs my attention this week?',
  'How is the budget tracking? Explain CPI and SPI.',
  'Which clients need a follow-up?',
  'What is left in the current phase?'
]

let nextId = 0
const id = () => `m${Date.now()}-${nextId++}`

/** The copilot chat. Each question goes to POST /assistant/chat with the
 * selected project (and client, if one is open), so the answer is grounded in
 * what is in the database. */
export const useAiCopilotStore = defineStore('aiCopilot', {
  state: () => ({
    isOpen: false,
    isThinking: false,
    messages: [] as CopilotMessage[]
  }),

  actions: {
    toggleOpen() {
      this.isOpen = !this.isOpen
    },

    setOpen(open: boolean) {
      this.isOpen = open
    },

    async ask(prompt: string, context: { projectId?: number | null; clientId?: number | null } = {}) {
      const text = prompt.trim()
      if (!text || this.isThinking) return
      this.messages.push({ id: id(), role: 'user', content: text, timestamp: new Date().toISOString() })
      this.isThinking = true
      try {
        const history = this.messages
          .filter(m => !m.error)
          .slice(-8)
          .map(m => ({ role: m.role, content: m.content }))
        const answer = await apiClient.post<{ reply: string; actions: CopilotAction[]; source: string }>(
          '/assistant/chat',
          { messages: history, project_id: context.projectId ?? null, client_id: context.clientId ?? null }
        )
        this.messages.push({
          id: id(),
          role: 'assistant',
          content: answer.reply,
          actions: answer.actions,
          source: answer.source,
          timestamp: new Date().toISOString()
        })
      } catch (err) {
        this.messages.push({
          id: id(),
          role: 'assistant',
          content: errorMessage(err, 'The copilot could not answer'),
          error: true,
          timestamp: new Date().toISOString()
        })
      } finally {
        this.isThinking = false
      }
    },

    markDone(messageId: string, label: string) {
      const message = this.messages.find(m => m.id === messageId)
      if (message) message.done = [...(message.done ?? []), label]
    },

    clearChat() {
      this.messages = []
    }
  }
})
