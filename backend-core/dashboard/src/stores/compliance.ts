import { defineStore } from 'pinia'
import { apiClient } from 'src/services/api'
import type { ComplianceSummary, Inspection, InspectionStatus, Permit, PermitStatus } from 'src/types/controls'

export interface PermitFields {
  permit_number: string | null
  permit_type: string
  description?: string | null
  jurisdiction?: string | null
  status: PermitStatus
  application_date?: string | null
  issued_date?: string | null
  expiration_date?: string | null
  permit_fee?: number
  conditions?: string | null
  contact_name?: string | null
  contact_phone?: string | null
  contact_email?: string | null
}

export interface InspectionFields {
  inspection_type: string
  description?: string | null
  permit_id?: number | null
  inspector_name?: string | null
  scheduled_date?: string | null
  status?: InspectionStatus
  result_details?: string | null
  critical_findings?: string | null
  requires_followup?: boolean
  followup_completed?: boolean
}

/** The selected project's permits and inspections. */
export const useComplianceStore = defineStore('compliance', {
  state: () => ({
    projectId: null as number | null,
    summary: null as ComplianceSummary | null,
    permits: [] as Permit[],
    inspections: [] as Inspection[],
    loading: false,
    error: null as string | null
  }),

  actions: {
    clear() {
      this.projectId = null
      this.summary = null
      this.permits = []
      this.inspections = []
    },

    async load(projectId: number) {
      this.projectId = projectId
      this.loading = true
      this.error = null
      try {
        const data = await apiClient.get<{ summary: ComplianceSummary; permits: Permit[]; inspections: Inspection[] }>(
          `/projects/${projectId}/compliance`
        )
        if (this.projectId !== projectId) return
        this.summary = data.summary
        this.permits = data.permits
        this.inspections = data.inspections
      } catch (err) {
        this.error = (err as Error).message
        throw err
      } finally {
        this.loading = false
      }
    },

    async reload() {
      if (this.projectId) await this.load(this.projectId)
    },

    async savePermit(fields: PermitFields, permitId?: number) {
      if (!this.projectId) return
      if (permitId) await apiClient.patch(`/projects/${this.projectId}/permits/${permitId}`, fields)
      else await apiClient.post(`/projects/${this.projectId}/permits`, fields)
      await this.reload()
    },

    async deletePermit(permitId: number) {
      if (!this.projectId) return
      await apiClient.delete(`/projects/${this.projectId}/permits/${permitId}`)
      await this.reload()
    },

    /** Create or update an inspection; the response says which schedule task a
     * result completed or which correction task it added. */
    async saveInspection(fields: Partial<InspectionFields>, inspectionId?: number): Promise<Inspection | undefined> {
      if (!this.projectId) return
      const result = inspectionId
        ? await apiClient.patch<Inspection>(`/projects/${this.projectId}/inspections/${inspectionId}`, fields)
        : await apiClient.post<Inspection>(`/projects/${this.projectId}/inspections`, fields)
      await this.reload()
      return result
    },

    async deleteInspection(inspectionId: number) {
      if (!this.projectId) return
      await apiClient.delete(`/projects/${this.projectId}/inspections/${inspectionId}`)
      await this.reload()
    }
  }
})
