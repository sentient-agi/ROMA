import React from 'react'
import { useTaskGraphStore } from '@/stores/taskGraphStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Workflow,
  GitBranch,
  Clock,
  Focus,
  Eye,
  EyeOff,
  ZoomIn,
  RotateCcw
} from 'lucide-react'
import { cn } from '@/lib/utils'

const ContextFlowPanel: React.FC = () => {
  const {
    selectedNodeId,
    nodes,
    showContextFlow,
    toggleContextFlow,
    contextFlowMode,
    setContextFlowMode,
    focusNodeId,
    setFocusNode,
    zoomToSubtree
  } = useTaskGraphStore()

  const hasNodes = Object.keys(nodes).length > 0
  const selectedNode = selectedNodeId ? nodes[selectedNodeId] : null

  const flowModes = [
    {
      id: 'none',
      label: 'None',
      icon: <EyeOff className="w-4 h-4" />,
      description: 'Show all nodes normally'
    },
    {
      id: 'dataFlow',
      label: 'Data Flow',
      icon: <Workflow className="w-4 h-4" />,
      description: 'Highlight data dependencies'
    },
    {
      id: 'executionPath',
      label: 'Execution Path',
      icon: <Clock className="w-4 h-4" />,
      description: 'Show execution sequence'
    },
    {
      id: 'subtree',
      label: 'Subtree',
      icon: <GitBranch className="w-4 h-4" />,
      description: 'Focus on node descendants'
    }
  ]

  return (
    <>
      {/* Desktop Layout */}
      <div className="hidden md:flex items-center space-x-2">
        {hasNodes && (
          <>
            {/* Context Flow Toggle */}
            <Button
              variant={showContextFlow ? "default" : "outline"}
              size="sm"
              onClick={toggleContextFlow}
              className="text-xs"
            >
              <Eye className="w-4 h-4 mr-1" />
              Context Flow
            </Button>

            {/* Flow Mode Selector */}
            {showContextFlow && (
              <div className="flex items-center space-x-1 border rounded-md p-1">
                {flowModes.map((mode) => (
                  <Button
                    key={mode.id}
                    variant={contextFlowMode === mode.id ? "default" : "ghost"}
                    size="sm"
                    onClick={() => setContextFlowMode(mode.id)}
                    className="h-8 px-2"
                    title={mode.description}
                  >
                    {mode.icon}
                    <span className="ml-1 text-xs">{mode.label}</span>
                  </Button>
                ))}
              </div>
            )}

            {/* Selected Node Actions */}
            {selectedNode && contextFlowMode !== 'none' && (
              <div className="flex items-center space-x-1 border rounded-md p-1 bg-muted/50">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setFocusNode(selectedNodeId)}
                  className="h-8 px-2"
                  title="Focus on selected node"
                >
                  <Focus className="w-4 h-4" />
                </Button>
                
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => zoomToSubtree(selectedNodeId!)}
                  className="h-8 px-2"
                  title="Zoom to subtree"
                >
                  <ZoomIn className="w-4 h-4" />
                </Button>

                <Badge variant="outline" className="text-xs">
                  {selectedNode.task_type}
                </Badge>
              </div>
            )}

            {/* Reset Focus */}
            {focusNodeId && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setFocusNode(undefined)}
                className="h-8 px-2"
                title="Reset focus"
              >
                <RotateCcw className="w-4 h-4" />
              </Button>
            )}
          </>
        )}
      </div>

      {/* Mobile Layout */}
      <div className="md:hidden w-full">
        {hasNodes && (
          <div className="space-y-3">
            {/* Context Flow Toggle Button */}
            <Button
              variant={showContextFlow ? "default" : "outline"}
              size="sm"
              onClick={toggleContextFlow}
              className="w-full justify-start text-xs"
            >
              <Eye className="w-4 h-4 mr-2" />
              Context Flow
            </Button>

            {/* Flow Mode Selector - 2x2 Grid */}
            {showContextFlow && (
              <div className="grid grid-cols-2 gap-2">
                {flowModes.map((mode) => (
                  <Button
                    key={mode.id}
                    variant={contextFlowMode === mode.id ? "default" : "outline"}
                    size="sm"
                    onClick={() => setContextFlowMode(mode.id)}
                    className="h-auto p-3 flex flex-col items-center space-y-1 text-xs"
                    title={mode.description}
                  >
                    {mode.icon}
                    <span className="text-center">{mode.label}</span>
                  </Button>
                ))}
              </div>
            )}

            {/* Selected Node Actions */}
            {selectedNode && contextFlowMode !== 'none' && (
              <div className="space-y-2">
                <div className="text-xs font-medium text-muted-foreground">
                  Selected Node: {selectedNode.task_type}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setFocusNode(selectedNodeId)}
                    className="h-auto p-3 flex flex-col items-center space-y-1 text-xs"
                  >
                    <Focus className="w-4 h-4" />
                    <span className="text-center">Focus</span>
                  </Button>
                  
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => zoomToSubtree(selectedNodeId!)}
                    className="h-auto p-3 flex flex-col items-center space-y-1 text-xs"
                  >
                    <ZoomIn className="w-4 h-4" />
                    <span className="text-center">Zoom</span>
                  </Button>
                </div>
              </div>
            )}

            {/* Reset Focus */}
            {focusNodeId && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFocusNode(undefined)}
                className="w-full justify-start text-xs"
              >
                <RotateCcw className="w-4 h-4 mr-2" />
                Reset Focus
              </Button>
            )}
          </div>
        )}
      </div>
    </>
  )
}

export default ContextFlowPanel 