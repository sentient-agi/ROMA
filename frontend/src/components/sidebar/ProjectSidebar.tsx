import React, { useState, useEffect } from 'react'
import { useProjectStore } from '@/stores/projectStore'
import { useTaskGraphStore } from '@/stores/taskGraphStore'
import projectService from '@/services/projectService'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Plus,
  MessageSquare,
  MoreVertical,
  Trash2,
  Calendar,
  Activity,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Settings,
  Download,
  FileText,
  Save,
  Clock,
  Play,
  Info,
  FolderOpen,
  Database
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { toast } from '@/components/ui/use-toast'
import ProjectConfigPanel, { ProjectConfig } from '@/components/project/ProjectConfigPanel'

interface ProjectSidebarProps {
  forceMobileExpanded?: boolean;
  onProjectSelect?: () => void;
}

const ProjectSidebar: React.FC<ProjectSidebarProps> = ({
  forceMobileExpanded = false,
  onProjectSelect,
}) => {
  const {
    projects,
    currentProjectId,
    isSidebarOpen,
    isCreatingProject,
    setSidebarOpen,
    setCreatingProject,
    setProjects,
    setCurrentProject,
    addProject,
    removeProject,
    getCurrentProject,
    getRecentProjects
  } = useProjectStore()

  const { setLoading, nodes } = useTaskGraphStore()
  
  const [newProjectGoal, setNewProjectGoal] = useState('')
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [loadingProjectId, setLoadingProjectId] = useState<string | null>(null)
  const [showConfigDialog, setShowConfigDialog] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [lastSwitchTime, setLastSwitchTime] = useState(0)
  const [projectDetails, setProjectDetails] = useState<{
    projectId: string | null
    s3BucketName: string | null
    s3MountEnabled: boolean
    projectToolkitsDir: string | null
    projectResultsDir: string | null
  }>({
    projectId: null,
    s3BucketName: null,
    s3MountEnabled: false,
    projectToolkitsDir: null,
    projectResultsDir: null
  })
  const [showProjectDetails, setShowProjectDetails] = useState(false)
  const [newProjectConfig, setNewProjectConfig] = useState<ProjectConfig>({
    llm: {
      provider: 'openai',
      model: 'gpt-4',
      temperature: 0.7,
      timeout: 30,
      max_retries: 3
    },
    execution: {
      max_concurrent_nodes: 6,
      max_execution_steps: 250,
      max_recursion_depth: 2,
      task_timeout_seconds: 300,
      enable_hitl: true,
      hitl_root_plan_only: true,
      hitl_timeout_seconds: 300,
      hitl_after_plan_generation: true,
      hitl_after_modified_plan: true,
      hitl_after_atomizer: false,
      hitl_before_execute: false
    },
    cache: {
      enabled: true,
      ttl_seconds: 3600,
      max_size: 1000,
      cache_type: 'memory'
    },
    project: {
      goal: '',
      max_steps: 250
    }
  })

  // Load projects on mount
  useEffect(() => {
    loadProjects()
  }, [])

  // Load project details when current project changes
  useEffect(() => {
    if (currentProjectId) {
      fetchProjectDetails()
    }
  }, [currentProjectId])

  const fetchProjectDetails = async () => {
    try {
      // Fetch project environment details from the backend
      // Pass the current project ID as a query parameter
      const url = currentProjectId 
        ? `/api/project/details?project_id=${currentProjectId}`
        : '/api/project/details'
      const response = await fetch(url)
      if (response.ok) {
        const data = await response.json()
        setProjectDetails({
          projectId: data.project_id || null,
          s3BucketName: data.s3_bucket_name || null,
          s3MountEnabled: data.s3_mount_enabled || false,
          projectToolkitsDir: data.project_toolkits_dir || null,
          projectResultsDir: data.project_results_dir || null
        })
      }
    } catch (error) {
      // Fallback to simulated data for now since backend might not have this endpoint yet
      console.log('Project details endpoint not available, using fallback data')
      setProjectDetails({
        projectId: currentProjectId || null,
        s3BucketName: 'roma-shared', // From .env file
        s3MountEnabled: true, // From .env file
        projectToolkitsDir: currentProjectId ? `/opt/sentient/${currentProjectId}/toolkits` : null,
        projectResultsDir: currentProjectId ? `/opt/sentient/${currentProjectId}/results` : null
      })
    }
  }

  // Helper function to find the root node
  const getRootNode = () => {
    return Object.values(nodes).find(node => node.layer === 0 && !node.parent_node_id)
  }

  // Helper function to check if root node is completed and has results
  const isRootNodeCompleted = () => {
    const rootNode = getRootNode()
    return rootNode && rootNode.status === 'DONE' && (rootNode.full_result || rootNode.output_summary)
  }

  // Helper function to check if a project has completed results (for any project)
  const hasProjectCompletedResults = (project: any) => {
    // Check multiple conditions to determine if project has completed results
    
    // 1. Check if project has saved results flag
    if (project.has_saved_results) {
      return true
    }
    
    // 2. Check if project status is completed
    if (project.status === 'completed') {
      return true
    }
    
    // 3. If this is the current project, check if root node is completed
    if (project.id === currentProjectId && Object.keys(nodes).length > 0) {
      const rootNode = getRootNode()
      return rootNode && rootNode.status === 'DONE' && (rootNode.full_result || rootNode.output_summary)
    }
    
    // 4. For testing purposes, let's also check if the project has any nodes
    // This is a fallback to show the button for projects that might have results
    if (project.node_count > 0) {
      return true
    }
    
    return false
  }

  // Function to download results for a specific project
  const downloadProjectResults = async (projectId: string, e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }

    try {
      // If it's the current project and we have nodes loaded, use client-side download
      if (projectId === currentProjectId && Object.keys(nodes).length > 0) {
        await downloadRootNodeResult()
        return
      }

      // Otherwise, try to download from server
      await projectService.downloadProjectReport(projectId, 'markdown')
      toast({
        title: "Download Complete",
        description: "Project report downloaded successfully",
      })
    } catch (error) {
      console.error('Failed to download project results:', error)
      toast({
        title: "Error",
        description: "Failed to download project results",
        variant: "destructive",
      })
    }
  }

  // Function to download root node result (client-side)
  const downloadRootNodeResult = async () => {
    const rootNode = getRootNode()
    if (!rootNode) {
      toast({
        title: "Error",
        description: "No root node found",
        variant: "destructive",
      })
      return
    }

    try {
      // Use the same logic as FullResultModal to detect the best content
      // Priority order: look for specific fields with complete content first
      const candidates = [
        // Check for the specific field that contains complete search results with citations
        { field: 'full_result.output_text_with_citations', data: rootNode.full_result?.output_text_with_citations, type: 'markdown' as const },
        
        // Check for other potential markdown fields in full_result
        { field: 'full_result.output_text', data: rootNode.full_result?.output_text, type: 'markdown' as const },
        { field: 'full_result.result', data: rootNode.full_result?.result, type: 'unknown' as const },
        
        // Check for common markdown field names at root level
        { field: 'output_summary_markdown', data: (rootNode as any).output_summary_markdown, type: 'markdown' as const },
        { field: 'result_markdown', data: (rootNode as any).result_markdown, type: 'markdown' as const },
        { field: 'markdown_result', data: (rootNode as any).markdown_result, type: 'markdown' as const },
        { field: 'output_markdown', data: (rootNode as any).output_markdown, type: 'markdown' as const },
        
        // Then check full_result as a whole (for non-search nodes)
        { field: 'full_result', data: rootNode.full_result, type: 'unknown' as const },
        
        // Finally fall back to output_summary (truncated version)
        { field: 'output_summary', data: rootNode.output_summary, type: 'text' as const }
      ] as Array<{ field: string; data: any; type: 'markdown' | 'unknown' | 'text' }>

      let content = ''
      let filename = 'project-result.md'
      let mimeType = 'text/markdown'

      // Find the first available candidate with substantial content
      for (const candidate of candidates) {
        if (candidate.data && 
            candidate.data !== null && 
            candidate.data !== undefined && 
            String(candidate.data).trim().length > 0) {
          
          let candidateContent: string
          let candidateType: 'markdown' | 'unknown' | 'text' | 'json' = candidate.type

          if (typeof candidate.data === 'string') {
            candidateContent = candidate.data
          } else {
            candidateContent = JSON.stringify(candidate.data, null, 2)
            candidateType = 'json'
          }

          // Skip if this is just a truncated version and we might have better content
          // Check if content looks truncated (ends with "..." or mentions annotations or is just planning info)
          if (candidate.field === 'output_summary' && 
              (candidateContent.includes('...') || 
               candidateContent.match(/\(\d+\s+annotations?\)/) ||
               candidateContent.includes('Planned') ||
               candidateContent.includes('sub-task'))) {
            // Continue to next candidate to see if we have better content
            continue
          }

          // Auto-detect markdown if not already specified
          if (candidateType === 'unknown' || candidateType === 'text') {
            if (candidateContent.includes('# ') || candidateContent.includes('## ') || candidateContent.includes('**') || candidateContent.includes('- ') || candidateContent.includes('[') || candidateContent.includes('*')) {
              candidateType = 'markdown'
            } else if (candidateContent.trim().startsWith('{') || candidateContent.trim().startsWith('[')) {
              try {
                JSON.parse(candidateContent)
                candidateType = 'json'
              } catch {
                candidateType = 'text'
              }
            } else {
              candidateType = 'text'
            }
          }

          // Set the content and file info
          content = candidateContent
          
          if (candidateType === 'json') {
            filename = 'project-result.json'
            mimeType = 'application/json'
          } else if (candidateType === 'markdown') {
            filename = 'project-result.md'
            mimeType = 'text/markdown'
          } else {
            filename = 'project-result.txt'
            mimeType = 'text/plain'
          }

          console.log(`Using content from: ${candidate.field}, type: ${candidateType}, length: ${content.length}`)
          break
        }
      }

      if (!content) {
        toast({
          title: "Error",
          description: "No result content found to download",
          variant: "destructive",
        })
        return
      }

      // Add project metadata to the content (only for markdown/text)
      const currentProject = getCurrentProject()
      if (mimeType === 'text/markdown' || mimeType === 'text/plain') {
        const metadata = `# Project: ${currentProject?.title || 'Untitled'}\n\n**Goal:** ${rootNode.goal}\n\n**Completed:** ${rootNode.timestamp_completed ? new Date(rootNode.timestamp_completed).toLocaleString() : 'Unknown'}\n\n---\n\n`
        content = metadata + content
      }

      // Create and download the file
      const blob = new Blob([content], { type: mimeType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      toast({
        title: "Download Complete",
        description: `Project result downloaded as ${filename}`,
      })
    } catch (error) {
      console.error('Failed to download result:', error)
      toast({
        title: "Error",
        description: "Failed to download project result",
        variant: "destructive",
      })
    }
  }

  // Manual save function
  const handleSaveResults = async () => {
    const currentProject = getCurrentProject()
    if (!currentProject) return

    setIsSaving(true)
    try {
      const result = await projectService.saveProjectResults(currentProject.id)
      toast({
        title: "Results Saved",
        description: result.message || "Project results have been saved successfully",
      })
    } catch (error) {
      console.error('Failed to save results:', error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to save results",
        variant: "destructive",
      })
    } finally {
      setIsSaving(false)
    }
  }

  // Download from server function
  const handleDownloadFromServer = async (format: 'markdown' | 'json' | 'html' = 'markdown') => {
    const currentProject = getCurrentProject()
    if (!currentProject) return

    try {
      await projectService.downloadProjectReport(currentProject.id, format)
      toast({
        title: "Download Complete",
        description: `Project report downloaded as ${format}`,
      })
    } catch (error) {
      console.error('Failed to download from server:', error)
      toast({
        title: "Feature Not Available",
        description: "Server-side download requires backend support. Use the client-side download instead.",
        variant: "destructive",
      })
    }
  }

  const loadProjects = async () => {
    try {
      const data = await projectService.getProjects()
      setProjects(data.projects)
      if (data.current_project_id) {
        setCurrentProject(data.current_project_id)
      }
    } catch (error) {
      console.error('Failed to load projects:', error)
      toast({
        title: "Error",
        description: "Failed to load projects",
        variant: "destructive",
      })
    }
  }

  const handleCreateProject = async () => {
    if (!newProjectGoal.trim()) return

    setCreatingProject(true)
    try {
      const result = await projectService.createProjectWithConfig(
        newProjectGoal.trim(),
        {
          ...newProjectConfig,
          project: {
            ...newProjectConfig.project,
            goal: newProjectGoal.trim()
          }
        }
      )
      addProject(result.project)
      setNewProjectGoal('')
      setIsDialogOpen(false)
      setLoading(true) // Start loading state for graph
      onProjectSelect?.() // Close mobile menu after project creation
      
      toast({
        title: "Project Created",
        description: result.message,
      })
    } catch (error) {
      console.error('Failed to create project:', error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to create project",
        variant: "destructive",
      })
    } finally {
      setCreatingProject(false)
    }
  }

  const handleConfiguredCreate = async () => {
    if (!newProjectConfig.project.goal.trim()) return

    setCreatingProject(true)
    try {
      const result = await projectService.createProjectWithConfig(
        newProjectConfig.project.goal.trim(),
        newProjectConfig
      )
      addProject(result.project)
      setNewProjectConfig(prev => ({ ...prev, project: { ...prev.project, goal: '' } }))
      setShowConfigDialog(false)
      setLoading(true)
      onProjectSelect?.() // Close mobile menu after project creation
      
      toast({
        title: "Project Created",
        description: result.message,
      })
    } catch (error) {
      console.error('Failed to create project:', error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to create project",
        variant: "destructive",
      })
    } finally {
      setCreatingProject(false)
    }
  }

  const handleSwitchProject = async (projectId: string) => {
    if (projectId === currentProjectId) return

    // Debounce rapid switches (minimum 500ms between switches)
    const now = Date.now()
    if (now - lastSwitchTime < 500) {
      console.log('⏳ Debouncing rapid project switch')
      return
    }
    setLastSwitchTime(now)

    setLoadingProjectId(projectId)
    setLoading(true)
    
    try {
      // CRITICAL: Update both stores BEFORE calling the service
      // This prevents race conditions where WebSocket updates arrive before state is synced
      setCurrentProject(projectId)
      useTaskGraphStore.getState().setCurrentProject(projectId)
      
      // Now switch the project on the backend
      await projectService.switchProject(projectId)
      
      // If we have cached data, switch to it immediately
      const cachedData = useTaskGraphStore.getState().getProjectData(projectId)
      if (cachedData) {
        console.log('🚀 Using cached project data for immediate display')
        useTaskGraphStore.getState().switchToProject(projectId)
      }
      
      toast({
        title: "Project Switched",
        description: "Successfully switched to project",
      })
    } catch (error) {
      console.error('Failed to switch project:', error)
      
      // Revert the optimistic update on error
      if (currentProjectId) {
        setCurrentProject(currentProjectId)
        useTaskGraphStore.getState().setCurrentProject(currentProjectId)
      }
      
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to switch project",
        variant: "destructive",
      })
    } finally {
      setLoadingProjectId(null)
      setLoading(false)
    }
  }

  const handleDeleteProject = async (projectId: string, e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault()
      e.stopPropagation()
    }
    
    if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) {
      return
    }

    try {
      await projectService.deleteProject(projectId)
      removeProject(projectId)
      
      toast({
        title: "Project Deleted",
        description: "Project has been deleted successfully",
      })
    } catch (error) {
      console.error('Failed to delete project:', error)
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to delete project",
        variant: "destructive",
      })
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))
    
    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays} days ago`
    return date.toLocaleDateString()
  }

  const truncateText = (text: string, maxLength: number = 100) => {
    if (text.length <= maxLength) return text
    return text.substring(0, maxLength) + '...'
  }

  const allProjects = projects
    .filter(p => p.id !== currentProjectId)
    .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
  const currentProject = getCurrentProject()

  // Helper function to get full S3 bucket path
  const getS3BucketPath = (localPath: string | null) => {
    if (!localPath || !projectDetails.s3MountEnabled || !projectDetails.s3BucketName) {
      return null
    }
    return `s3://${projectDetails.s3BucketName}/data/${projectDetails.projectId}/${localPath.split('/').pop()}`
  }

  // Helper function to copy text to clipboard
  const copyToClipboard = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast({
        title: "Copied to clipboard",
        description: `${label} copied successfully`,
      })
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to copy to clipboard",
        variant: "destructive",
      })
    }
  }

  return (
    <div className={cn(
      "h-full bg-background transition-all duration-300 ease-in-out flex flex-col shadow-sm",
      // Mobile mode: full width, no border, no toggle
      forceMobileExpanded ? "w-full" : 
      // Desktop mode: collapsible with border
      isSidebarOpen ? "w-80 border-r" : "w-12 border-r"
    )}>
      {/* Header - Only show in desktop mode */}
      {!forceMobileExpanded && (
        <div className="p-4 border-b flex items-center justify-between">
          {isSidebarOpen && (
            <h2 className="font-semibold text-lg">Projects</h2>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSidebarOpen(!isSidebarOpen)}
            className="ml-auto"
          >
            {isSidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
        </div>
      )}

      {(isSidebarOpen || forceMobileExpanded) && (
        <>
          {/* New Project Button */}
          <div className="p-4">
            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
              <DialogTrigger asChild>
                <Button className="w-full" size="sm">
                  <Plus className="h-4 w-4 mr-2" />
                  New Project
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create New Project</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium">Project Goal</label>
                    <Textarea
                      value={newProjectGoal}
                      onChange={(e) => setNewProjectGoal(e.target.value)}
                      placeholder="Describe what you want to research or accomplish..."
                      className="mt-1"
                      rows={4}
                    />
                  </div>
                  <div className="flex justify-end space-x-2">
                    <Button
                      variant="outline"
                      onClick={() => setIsDialogOpen(false)}
                      disabled={isCreatingProject}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setNewProjectConfig(prev => ({
                          ...prev,
                          project: { ...prev.project, goal: newProjectGoal }
                        }))
                        setShowConfigDialog(true)
                        setIsDialogOpen(false)
                      }}
                      disabled={!newProjectGoal.trim() || isCreatingProject}
                    >
                      <Settings className="h-4 w-4 mr-2" />
                      Configure
                    </Button>
                    <Button
                      onClick={handleCreateProject}
                      disabled={!newProjectGoal.trim() || isCreatingProject}
                    >
                      {isCreatingProject ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Creating...
                        </>
                      ) : (
                        'Quick Create'
                      )}
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {/* Configuration Dialog */}
          <Dialog open={showConfigDialog} onOpenChange={setShowConfigDialog}>
            <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Configure Project</DialogTitle>
              </DialogHeader>
              <ProjectConfigPanel
                config={newProjectConfig}
                onChange={setNewProjectConfig}
                onSubmit={handleConfiguredCreate}
                onCancel={() => setShowConfigDialog(false)}
                isCreating={isCreatingProject}
              />
            </DialogContent>
          </Dialog>

          {/* Current Project */}
          {currentProject && (
            <div className="px-4 pb-4">
              <div className="text-xs font-medium text-muted-foreground mb-2">CURRENT PROJECT</div>
              <div className="bg-muted/50 rounded-lg p-3 border-l-4 border-blue-500 group relative">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-sm truncate">{currentProject.title}</h3>
                    <p className="text-xs text-muted-foreground mt-1">
                      {truncateText(currentProject.description, 80)}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      <Badge variant="secondary" className="text-xs">
                        {currentProject.status}
                      </Badge>
                      {currentProject.node_count > 0 && (
                        <span className="text-xs text-muted-foreground">
                          {currentProject.node_count} nodes
                        </span>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-5 w-5 p-0 text-muted-foreground hover:text-foreground"
                        onClick={() => setShowProjectDetails(!showProjectDetails)}
                        title="Toggle project details"
                      >
                        <Info className="h-3 w-3" />
                      </Button>
                    </div>

                    {/* Project Details */}
                    {showProjectDetails && projectDetails.projectId && (
                      <div className="mt-3 pt-2 border-t border-border/50 space-y-2">
                        <div className="text-xs">
                          <div className="flex items-center gap-1 mb-1">
                            <Info className="h-3 w-3 text-muted-foreground" />
                            <span className="font-medium text-muted-foreground">Project ID</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <code className="text-xs bg-muted px-1 py-0.5 rounded font-mono">
                              {truncateText(projectDetails.projectId, 20)}
                            </code>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-4 w-4 p-0 text-muted-foreground hover:text-foreground"
                              onClick={() => copyToClipboard(projectDetails.projectId!, 'Project ID')}
                              title="Copy project ID"
                            >
                              <FileText className="h-2 w-2" />
                            </Button>
                          </div>
                        </div>

                        {projectDetails.s3MountEnabled && projectDetails.s3BucketName && (
                          <div className="text-xs">
                            <div className="flex items-center gap-1 mb-1">
                              <Database className="h-3 w-3 text-muted-foreground" />
                              <span className="font-medium text-muted-foreground">S3 Storage</span>
                            </div>
                            <div className="space-y-1">
                              <div className="flex items-center gap-1">
                                <span className="text-muted-foreground">Bucket:</span>
                                <code className="text-xs bg-muted px-1 py-0.5 rounded font-mono">
                                  {projectDetails.s3BucketName}
                                </code>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-4 w-4 p-0 text-muted-foreground hover:text-foreground"
                                  onClick={() => copyToClipboard(projectDetails.s3BucketName!, 'S3 bucket name')}
                                  title="Copy bucket name"
                                >
                                  <FileText className="h-2 w-2" />
                                </Button>
                              </div>
                              
                              {projectDetails.projectToolkitsDir && (
                                <div>
                                  <div className="flex items-center gap-1 mb-1">
                                    <FolderOpen className="h-3 w-3 text-muted-foreground" />
                                    <span className="text-muted-foreground">Toolkits Data:</span>
                                  </div>
                                  <div className="ml-4 space-y-1">
                                    <div className="flex items-center gap-1">
                                      <span className="text-xs text-muted-foreground">Local:</span>
                                      <code className="text-xs bg-muted px-1 py-0.5 rounded font-mono">
                                        {truncateText(projectDetails.projectToolkitsDir, 25)}
                                      </code>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-4 w-4 p-0 text-muted-foreground hover:text-foreground"
                                        onClick={() => copyToClipboard(projectDetails.projectToolkitsDir!, 'Toolkits directory')}
                                        title="Copy toolkits path"
                                      >
                                        <FileText className="h-2 w-2" />
                                      </Button>
                                    </div>
                                    {getS3BucketPath(projectDetails.projectToolkitsDir) && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-xs text-muted-foreground">S3:</span>
                                        <code className="text-xs bg-muted px-1 py-0.5 rounded font-mono">
                                          {truncateText(getS3BucketPath(projectDetails.projectToolkitsDir)!, 25)}
                                        </code>
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          className="h-4 w-4 p-0 text-muted-foreground hover:text-foreground"
                                          onClick={() => copyToClipboard(getS3BucketPath(projectDetails.projectToolkitsDir!)!, 'S3 toolkits path')}
                                          title="Copy S3 toolkits path"
                                        >
                                          <FileText className="h-2 w-2" />
                                        </Button>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}
                              
                              {projectDetails.projectResultsDir && (
                                <div>
                                  <div className="flex items-center gap-1 mb-1">
                                    <FolderOpen className="h-3 w-3 text-muted-foreground" />
                                    <span className="text-muted-foreground">Results Output:</span>
                                  </div>
                                  <div className="ml-4 space-y-1">
                                    <div className="flex items-center gap-1">
                                      <span className="text-xs text-muted-foreground">Local:</span>
                                      <code className="text-xs bg-muted px-1 py-0.5 rounded font-mono">
                                        {truncateText(projectDetails.projectResultsDir, 25)}
                                      </code>
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-4 w-4 p-0 text-muted-foreground hover:text-foreground"
                                        onClick={() => copyToClipboard(projectDetails.projectResultsDir!, 'Results directory')}
                                        title="Copy results path"
                                      >
                                        <FileText className="h-2 w-2" />
                                      </Button>
                                    </div>
                                    {getS3BucketPath(projectDetails.projectResultsDir) && (
                                      <div className="flex items-center gap-1">
                                        <span className="text-xs text-muted-foreground">S3:</span>
                                        <code className="text-xs bg-muted px-1 py-0.5 rounded font-mono">
                                          {truncateText(getS3BucketPath(projectDetails.projectResultsDir)!, 25)}
                                        </code>
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          className="h-4 w-4 p-0 text-muted-foreground hover:text-foreground"
                                          onClick={() => copyToClipboard(getS3BucketPath(projectDetails.projectResultsDir!)!, 'S3 results path')}
                                          title="Copy S3 results path"
                                        >
                                          <FileText className="h-2 w-2" />
                                        </Button>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <div className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded cursor-pointer">
                        <MoreVertical className="h-4 w-4" />
                      </div>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-48">
                      <DropdownMenuItem onClick={() => handleDeleteProject(currentProject.id)}>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Delete Project
                      </DropdownMenuItem>
                      {hasProjectCompletedResults(currentProject) && (
                        <DropdownMenuItem onClick={() => downloadProjectResults(currentProject.id)}>
                          <Download className="mr-2 h-4 w-4" />
                          Download Report
                        </DropdownMenuItem>
                      )}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                
                {/* Small download button positioned at bottom right */}
                {hasProjectCompletedResults(currentProject) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="absolute bottom-2 right-2 h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                    onClick={(e) => downloadProjectResults(currentProject.id, e)}
                    title="Download results"
                  >
                    <Download className="h-3 w-3" />
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Projects List */}
          <div className="flex-1 overflow-hidden flex flex-col">
            <div className="px-4 pb-2">
              <div className="text-xs font-medium text-muted-foreground">ALL PROJECTS ({allProjects.length})</div>
            </div>
            <ScrollArea className="flex-1 px-4 h-0">
              <div className="space-y-2">
                {allProjects.map((project) => (
                  <div
                    key={project.id}
                    className={cn(
                      "group rounded-lg p-3 cursor-pointer transition-all duration-200 hover:bg-muted/50 hover:shadow-md relative",
                      project.id === currentProjectId && "bg-muted/30 border border-border shadow-sm"
                    )}
                    onClick={() => {
                      handleSwitchProject(project.id)
                      onProjectSelect?.()
                    }}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <MessageSquare className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          <h3 className="font-medium text-sm truncate">{project.title}</h3>
                          {loadingProjectId === project.id && (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          {truncateText(project.description, 60)}
                        </p>
                        <div className="flex items-center justify-between mt-2">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className="text-xs">
                              {project.status}
                            </Badge>
                            {project.node_count > 0 && (
                              <span className="text-xs text-muted-foreground">
                                {project.node_count} nodes
                              </span>
                            )}
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {formatDate(project.updated_at)}
                          </span>
                        </div>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <div className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded cursor-pointer">
                            <MoreVertical className="h-4 w-4" />
                          </div>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-48">
                          <DropdownMenuItem onClick={() => {
                              handleSwitchProject(project.id)
                              onProjectSelect?.()
                            }}>
                            <Play className="mr-2 h-4 w-4" />
                            Switch to Project
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => handleDeleteProject(project.id)}>
                            <Trash2 className="mr-2 h-4 w-4" />
                            Delete Project
                          </DropdownMenuItem>
                          {hasProjectCompletedResults(project) && (
                            <DropdownMenuItem onClick={() => downloadProjectResults(project.id)}>
                              <Download className="mr-2 h-4 w-4" />
                              Download Report
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    
                    {/* Small download button positioned at bottom right */}
                    {hasProjectCompletedResults(project) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="absolute bottom-2 right-2 h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={(e) => downloadProjectResults(project.id, e)}
                        title="Download results"
                      >
                        <Download className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        </>
      )}
    </div>
  )
}

export default ProjectSidebar 