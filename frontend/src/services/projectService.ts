import type { Project } from '@/stores/projectStore'
import type { ProjectConfig } from '@/components/project/ProjectConfigPanel'

interface SavedProjectSummary {
  project_id: string
  title: string
  saved_at: string
  completion_status: string
  total_nodes: number
  auto_saved: boolean
}

interface ProjectResults {
  project: Project
  saved_at: string
  graph_data: any
  metadata: {
    total_nodes: number
    project_goal: string
    completion_status: string
  }
}

class ProjectService {
  private baseUrl = '/api'

  // FIXED: Helper method to safely get store instances using our existing debug setup
  private getStores() {
    try {
      // Use our existing debug functions to access stores
      if (typeof window !== 'undefined' && (window as any).getProjectStoreState) {
        // Get current state through debug function
        const currentState = (window as any).getProjectStoreState()
        
        // Access the store methods through our debug setup
        const taskGraphStore = {
          setCurrentProject: (window as any).switchToProject,
          setProjectData: (window as any).setProjectData || (() => {}),
          getProjectData: (projectId: string) => {
            const state = (window as any).getProjectStoreState()
            return state.projectData[projectId] || null
          },
          clearProjectData: (projectId: string) => {
            // This would need to be implemented in the debug setup
            console.log('clearProjectData called for:', projectId)
          }
        }
        
        const projectStore = {
          setCurrentProject: (projectId: string) => {
            console.log('ProjectStore setCurrentProject called:', projectId)
          },
          addProject: (project: any) => {
            console.log('ProjectStore addProject called:', project)
          },
          removeProject: (projectId: string) => {
            console.log('ProjectStore removeProject called:', projectId)
          },
          currentProjectId: currentState.currentProjectId
        }
        
        return { taskGraphStore, projectStore }
      }
      
      return null
    } catch (error) {
      console.warn('Could not access stores:', error)
      return null
    }
  }

  async getProjects(): Promise<{ projects: Project[], current_project_id?: string }> {
    try {
      const response = await fetch(`${this.baseUrl}/projects`)
      if (!response.ok) {
        // If the endpoint doesn't exist or fails, return empty projects list
        if (response.status === 404 || response.status === 500) {
          console.warn('Projects endpoint not available, returning empty list')
          return { projects: [] }
        }
        throw new Error('Failed to fetch projects')
      }
      return response.json()
    } catch (error) {
      console.warn('Failed to fetch projects, returning empty list:', error)
      return { projects: [] }
    }
  }

  async createProject(goal: string, maxSteps: number = 250): Promise<{ project: Project, message: string }> {
    const response = await fetch(`${this.baseUrl}/projects`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ goal, max_steps: maxSteps }),
    })
    
    if (!response.ok) {
      let error
      try {
        error = await response.json()
      } catch (jsonError) {
        // If response is not JSON, create a generic error message
        error = { error: `HTTP ${response.status}: ${response.statusText || 'Failed to create project'}` }
      }
      throw new Error(error.error || 'Failed to create project')
    }
    
    const result = await response.json()
    
    // NEW: Update stores when project is created
    if (result.project) {
      const stores = this.getStores()
      if (stores) {
        // Add to project store
        stores.projectStore.addProject(result.project)
        
        // Switch to the new project
        stores.taskGraphStore.setCurrentProject(result.project.id)
        stores.projectStore.setCurrentProject(result.project.id)
      }
    }
    
    return result
  }

  async createProjectWithConfig(goal: string, config: ProjectConfig): Promise<{ project: Project, message: string }> {
    try {
      const response = await fetch(`${this.baseUrl}/projects/configured`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          goal, 
          config,
          max_steps: config.project.max_steps 
        }),
      })
      
      if (!response.ok) {
        let error
        try {
          error = await response.json()
        } catch (jsonError) {
          // If response is not JSON, create a generic error message
          error = { error: `HTTP ${response.status}: ${response.statusText || 'Failed to create configured project'}` }
        }
        throw new Error(error.error || 'Failed to create configured project')
      }
      
      const result = await response.json()
      
      // NEW: Update stores when configured project is created
      if (result.project) {
        const stores = this.getStores()
        if (stores) {
          // Add to project store
          stores.projectStore.addProject(result.project)
          
          // Switch to the new project
          stores.taskGraphStore.setCurrentProject(result.project.id)
          stores.projectStore.setCurrentProject(result.project.id)
        }
      }
      
      return result
    } catch (error) {
      // Fallback to regular project creation if configured endpoint doesn't exist
      console.warn('Configured project creation not available, falling back to regular creation')
      return this.createProject(goal, config.project.max_steps)
    }
  }

  async getProject(projectId: string): Promise<{ project: Project, state?: any }> {
    const response = await fetch(`${this.baseUrl}/projects/${projectId}`)
    if (!response.ok) {
      throw new Error('Failed to fetch project')
    }
    return response.json()
  }

  // UPDATED: Enhanced project switching with store integration
  async switchProject(projectId: string): Promise<{ project: Project, message: string }> {
    console.log('🔄 PROJECT SERVICE: Switching to project:', projectId)
    
    // Update frontend stores immediately for responsive UI
    const stores = this.getStores()
    if (stores) {
      // Set current project in both stores
      stores.projectStore.setCurrentProject(projectId)
      stores.taskGraphStore.setCurrentProject(projectId)
    }
    
    // Try WebSocket first for real-time switching
    if ((window as any).webSocketService?.isConnected()) {
      console.log('🔄 Using WebSocket for project switch:', projectId)
      
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          reject(new Error('Project switch timeout'))
        }, 10000) // 10 second timeout

        // Listen for success
        const handleSuccess = (data: any) => {
          clearTimeout(timeout)
          ;(window as any).webSocketService.socket?.off('project_switch_success', handleSuccess)
          ;(window as any).webSocketService.socket?.off('project_switch_error', handleError)
          
          console.log('✅ PROJECT SERVICE: WebSocket switch successful:', data)
          
          resolve({
            project: data.project_data?.current_project || { id: projectId },
            message: data.message || 'Project switched successfully'
          })
        }

        // Listen for error
        const handleError = (data: any) => {
          clearTimeout(timeout)
          ;(window as any).webSocketService.socket?.off('project_switch_success', handleSuccess)
          ;(window as any).webSocketService.socket?.off('project_switch_error', handleError)
          
          console.error('❌ PROJECT SERVICE: WebSocket switch failed:', data)
          reject(new Error(data.error || 'Failed to switch project'))
        }

        // Set up listeners
        ;(window as any).webSocketService.socket?.on('project_switch_success', handleSuccess)
        ;(window as any).webSocketService.socket?.on('project_switch_error', handleError)

        // Send switch request
        ;(window as any).webSocketService.switchProject(projectId)
      })
    } else {
      // Fallback to REST API
      console.log('🔄 Using REST API for project switch (WebSocket not connected):', projectId)
      
      try {
        const response = await fetch(`${this.baseUrl}/projects/${projectId}/switch`, {
          method: 'POST',
        })
        
        if (!response.ok) {
          const error = await response.json()
          throw new Error(error.error || 'Failed to switch project')
        }
        
        const result = await response.json()
        console.log('✅ PROJECT SERVICE: REST API switch successful:', result)
        return result
      } catch (error) {
        console.error('❌ PROJECT SERVICE: REST API switch failed:', error)
        throw error
      }
    }
  }

  // NEW: Switch to project and load its data
  async switchToProjectWithData(projectId: string): Promise<{ project: Project, message: string }> {
    console.log('🔄 PROJECT SERVICE: Switching to project with data loading:', projectId)
    
    try {
      // First switch the project
      const switchResult = await this.switchProject(projectId)
      
      // Then try to load any saved results for this project
      try {
        const savedResults = await this.loadProjectResults(projectId)
        if (savedResults.graph_data) {
          console.log('📊 PROJECT SERVICE: Loading saved project data')
          const stores = this.getStores()
          if (stores) {
            stores.taskGraphStore.setProjectData(projectId, savedResults.graph_data)
          }
        }
      } catch (error) {
        console.log('📊 PROJECT SERVICE: No saved data found for project (this is normal for new projects)')
      }
      
      return switchResult
    } catch (error) {
      console.error('❌ PROJECT SERVICE: Failed to switch to project with data:', error)
      throw error
    }
  }

  async deleteProject(projectId: string): Promise<{ message: string }> {
    const response = await fetch(`${this.baseUrl}/projects/${projectId}`, {
      method: 'DELETE',
    })
    
    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.error || 'Failed to delete project')
    }
    
    // NEW: Update stores when project is deleted
    const stores = this.getStores()
    if (stores) {
      // Remove from project store
      stores.projectStore.removeProject(projectId)
      
      // Clear project data from task graph store
      stores.taskGraphStore.clearProjectData(projectId)
      
      // If this was the current project, clear current project
      if (stores.projectStore.currentProjectId === projectId) {
        stores.projectStore.setCurrentProject(undefined)
        stores.taskGraphStore.setCurrentProject(undefined)
      }
    }
    
    return response.json()
  }

  // UPDATED: Enhanced save with store integration
  async saveProjectResults(projectId: string): Promise<{ message: string, saved_at: string, metadata: any }> {
    console.log('💾 PROJECT SERVICE: Saving project results:', projectId)
    
    try {
      // Get current project data from store
      const stores = this.getStores()
      const projectData = stores ? stores.taskGraphStore.getProjectData(projectId) : null
      
      const response = await fetch(`${this.baseUrl}/projects/${projectId}/save-results`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          graph_data: projectData,
          metadata: {
            saved_from_frontend: true,
            node_count: projectData?.all_nodes ? Object.keys(projectData.all_nodes).length : 0,
            project_goal: projectData?.overall_project_goal
          }
        }),
      })
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Failed to save project results')
      }
      
      const result = await response.json()
      console.log('✅ PROJECT SERVICE: Project results saved successfully')
      return result
    } catch (error) {
      // Fallback: save to localStorage if backend endpoint doesn't exist
      console.warn('💾 Backend save not available, using localStorage fallback')
      const stores = this.getStores()
      const projectData = stores ? stores.taskGraphStore.getProjectData(projectId) : null
      
      const timestamp = new Date().toISOString()
      const fallbackData = {
        message: "Results saved locally",
        saved_at: timestamp,
        metadata: { 
          local_save: true,
          node_count: projectData?.all_nodes ? Object.keys(projectData.all_nodes).length : 0,
          project_goal: projectData?.overall_project_goal
        },
        graph_data: projectData
      }
      localStorage.setItem(`project_${projectId}_results`, JSON.stringify(fallbackData))
      console.log('✅ PROJECT SERVICE: Project results saved to localStorage')
      return fallbackData
    }
  }

  // UPDATED: Enhanced load with store integration
  async loadProjectResults(projectId: string): Promise<ProjectResults> {
    console.log('📂 PROJECT SERVICE: Loading project results:', projectId)
    
    try {
      const response = await fetch(`${this.baseUrl}/projects/${projectId}/load-results`)
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Failed to load project results')
      }
      
      const result = await response.json()
      
      // NEW: Update store with loaded data
      if (result.graph_data) {
        const stores = this.getStores()
        if (stores) {
          stores.taskGraphStore.setProjectData(projectId, result.graph_data)
          console.log('✅ PROJECT SERVICE: Loaded project data into store')
        }
      }
      
      return result
    } catch (error) {
      // Fallback: load from localStorage
      console.warn('📂 Backend load not available, trying localStorage fallback')
      const localData = localStorage.getItem(`project_${projectId}_results`)
      
      if (localData) {
        const parsedData = JSON.parse(localData)
        
        // Update store with loaded data
        if (parsedData.graph_data) {
          const stores = this.getStores()
          if (stores) {
            stores.taskGraphStore.setProjectData(projectId, parsedData.graph_data)
            console.log('✅ PROJECT SERVICE: Loaded project data from localStorage into store')
          }
        }
        
        return {
          project: { id: projectId } as Project,
          saved_at: parsedData.saved_at,
          graph_data: parsedData.graph_data,
          metadata: parsedData.metadata
        }
      }
      
      throw error
    }
  }

  // NEW: Download project report (with fallback)
  async downloadProjectReport(projectId: string, format: 'markdown' | 'json' | 'html' = 'markdown'): Promise<void> {
    try {
      const response = await fetch(`${this.baseUrl}/projects/${projectId}/download-report?format=${format}`)
      
      if (!response.ok) {
        throw new Error('Backend download not available')
      }
      
      // Get filename from response headers
      const contentDisposition = response.headers.get('content-disposition')
      let filename = `project-report.${format}`
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="(.+)"/)
        if (filenameMatch) {
          filename = filenameMatch[1]
        }
      }
      
      // Download the file
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (error) {
      console.warn('Backend download not available, this feature requires backend support')
      throw new Error('Download from server requires backend support. Use the client-side download instead.')
    }
  }

  // NEW: Get saved projects summary (with fallback)
  async getSavedProjectsSummary(): Promise<SavedProjectSummary[]> {
    try {
      const response = await fetch(`${this.baseUrl}/projects/saved-summary`)
      
      if (!response.ok) {
        throw new Error('Failed to fetch saved projects summary')
      }
      
      return response.json()
    } catch (error) {
      console.warn('Saved projects summary not available from backend')
      return []
    }
  }

  async getRunningExecutions(): Promise<any> {
    try {
      const response = await fetch(`${this.baseUrl}/executions`)
      if (!response.ok) {
        return {}
      }
      return response.json()
    } catch (error) {
      console.warn('Failed to get running executions:', error)
      return {}
    }
  }
}

// Make service available globally for debugging
if (typeof window !== 'undefined') {
  (window as any).projectService = new ProjectService()
}

export default new ProjectService() 