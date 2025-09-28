import React from 'react'
import { useTaskGraphStore } from '@/stores/taskGraphStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Filter,
  X,
  Search,
  Eye,
  AlertTriangle,
  CheckCircle,
  Layers,
  RotateCcw,
  ChevronLeft
} from 'lucide-react'
import { cn } from '@/lib/utils'

const FilterPanel: React.FC = () => {
  const {
    filters,
    isFilterPanelOpen,
    updateFilters,
    resetFilters,
    toggleFilterPanel,
    setSearchTerm,
    getAvailableFilters,
    getFilteredNodes,
    nodes,
    // Quick filter actions
    showActiveNodes,
    showProblematicNodes,
    showCompletedNodes,
    showCurrentLayer
  } = useTaskGraphStore()

  const availableFilters = getAvailableFilters()
  const filteredNodes = getFilteredNodes()
  const totalNodes = Object.keys(nodes).length
  const filteredCount = Object.keys(filteredNodes).length
  const hasActiveFilters = Object.values(filters).some(filter => 
    Array.isArray(filter) ? filter.length > 0 : filter
  )

  const handleStatusToggle = (status: string) => {
    const newStatuses = filters.statuses.includes(status)
      ? filters.statuses.filter(s => s !== status)
      : [...filters.statuses, status]
    updateFilters({ statuses: newStatuses })
  }

  const handleTaskTypeToggle = (taskType: string) => {
    const newTaskTypes = filters.taskTypes.includes(taskType)
      ? filters.taskTypes.filter(t => t !== taskType)
      : [...filters.taskTypes, taskType]
    updateFilters({ taskTypes: newTaskTypes })
  }

  const handleLayerToggle = (layer: number) => {
    const newLayers = filters.layers.includes(layer)
      ? filters.layers.filter(l => l !== layer)
      : [...filters.layers, layer]
    updateFilters({ layers: newLayers })
  }

  const handleAgentToggle = (agent: string) => {
    const newAgents = filters.agentNames.includes(agent)
      ? filters.agentNames.filter(a => a !== agent)
      : [...filters.agentNames, agent]
    updateFilters({ agentNames: newAgents })
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'DONE': return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
      case 'RUNNING': return 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300'
      case 'FAILED': return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
      case 'READY': return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
      case 'NEEDS_REPLAN': return 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
      default: return 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300'
    }
  }

  // Simple checkbox component using HTML input
  const SimpleCheckbox: React.FC<{ 
    checked: boolean; 
    onChange: () => void; 
    label: React.ReactNode;
    className?: string;
  }> = ({ checked, onChange, label, className }) => (
    <label className={cn("flex items-center space-x-2 cursor-pointer hover:bg-muted/50 p-1 rounded", className)}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
      />
      {label}
    </label>
  )

  return (
    <>
      {/* Desktop Filter Trigger Button */}
      <div className="hidden md:block">
        <Button
          variant={hasActiveFilters ? "default" : "outline"}
          size="sm"
          onClick={toggleFilterPanel}
          className="relative"
        >
          <Filter className="w-4 h-4 mr-2" />
          Filter
          {hasActiveFilters && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5 text-xs">
              {filteredCount}/{totalNodes}
            </Badge>
          )}
        </Button>
      </div>

      {/* Mobile Filter Trigger Button */}
      <div className="md:hidden">
        <Button
          variant={hasActiveFilters ? "default" : "outline"}
          size="sm"
          onClick={toggleFilterPanel}
          className="w-full justify-start text-xs"
        >
          <Filter className="w-4 h-4 mr-2" />
          Filter
          {hasActiveFilters && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5 text-xs">
              {filteredCount}/{totalNodes}
            </Badge>
          )}
        </Button>
      </div>

      {/* Filter Panel Dialog */}
      <Dialog open={isFilterPanelOpen} onOpenChange={toggleFilterPanel}>
        <DialogContent className="max-w-sm h-[90vh] flex flex-col p-0">
          {/* Header */}
          <DialogHeader className="p-6 pb-4 border-b">
            <div className="flex items-center justify-between">
              <div>
                <DialogTitle>Graph Filters</DialogTitle>
                <DialogDescription>
                  Showing {filteredCount} of {totalNodes} nodes
                </DialogDescription>
              </div>
              {hasActiveFilters && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={resetFilters}
                  className="h-8 px-2"
                >
                  <RotateCcw className="w-4 h-4 mr-1" />
                  Reset
                </Button>
              )}
            </div>
          </DialogHeader>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* Quick Filters */}
            <div>
              <h4 className="text-sm font-medium mb-3">Quick Filters</h4>
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={showActiveNodes}
                  className="justify-start h-8"
                >
                  <Eye className="w-3 h-3 mr-2" />
                  Active
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={showProblematicNodes}
                  className="justify-start h-8"
                >
                  <AlertTriangle className="w-3 h-3 mr-2" />
                  Issues
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={showCompletedNodes}
                  className="justify-start h-8"
                >
                  <CheckCircle className="w-3 h-3 mr-2" />
                  Done
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={showCurrentLayer}
                  className="justify-start h-8"
                >
                  <Layers className="w-3 h-3 mr-2" />
                  Layer
                </Button>
              </div>
            </div>

            {/* Search */}
            <div>
              <h4 className="text-sm font-medium mb-3">Search</h4>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  placeholder="Search goals, results, agents..."
                  value={filters.searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9"
                />
                {filters.searchTerm && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSearchTerm('')}
                    className="absolute right-1 top-1/2 transform -translate-y-1/2 h-6 w-6 p-0"
                  >
                    <X className="w-3 h-3" />
                  </Button>
                )}
              </div>
            </div>

            {/* Status Filter */}
            {availableFilters.statuses.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-3">Status</h4>
                <div className="space-y-1">
                  {availableFilters.statuses.map((status) => (
                    <SimpleCheckbox
                      key={status}
                      checked={filters.statuses.includes(status)}
                      onChange={() => handleStatusToggle(status)}
                      label={
                        <Badge className={cn("text-xs", getStatusColor(status))}>
                          {status}
                        </Badge>
                      }
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Task Type Filter */}
            {availableFilters.taskTypes.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-3">Task Type</h4>
                <div className="space-y-1">
                  {availableFilters.taskTypes.map((taskType) => (
                    <SimpleCheckbox
                      key={taskType}
                      checked={filters.taskTypes.includes(taskType)}
                      onChange={() => handleTaskTypeToggle(taskType)}
                      label={<span className="text-sm">{taskType}</span>}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Layer Filter */}
            {availableFilters.layers.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-3">Layer</h4>
                <div className="space-y-1">
                  {availableFilters.layers.map((layer) => (
                    <SimpleCheckbox
                      key={layer}
                      checked={filters.layers.includes(layer)}
                      onChange={() => handleLayerToggle(layer)}
                      label={<span className="text-sm">Layer {layer}</span>}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Agent Filter */}
            {availableFilters.agentNames.length > 0 && (
              <div>
                <h4 className="text-sm font-medium mb-3">Agent</h4>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {availableFilters.agentNames.map((agent) => (
                    <SimpleCheckbox
                      key={agent}
                      checked={filters.agentNames.includes(agent)}
                      onChange={() => handleAgentToggle(agent)}
                      label={<span className="text-sm truncate">{agent}</span>}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default FilterPanel 