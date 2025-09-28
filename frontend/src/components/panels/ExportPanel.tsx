import React, { useState } from 'react'
import { useTaskGraphStore } from '@/stores/taskGraphStore'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Download,
  Image,
  FileText,
  Database,
  Archive,
  FileSpreadsheet,
  Camera,
  CheckCircle,
  AlertCircle
} from 'lucide-react'
import {
  exportGraphAsImage,
  exportNodesAsJSON,
  exportNodesAsCSV,
  exportNodeResults,
  exportProjectReport
} from '@/lib/exportUtils'

const ExportPanel: React.FC = () => {
  const {
    nodes,
    getFilteredNodes,
    overallProjectGoal,
    filters
  } = useTaskGraphStore()

  const [isOpen, setIsOpen] = useState(false)
  const [isExporting, setIsExporting] = useState<string | null>(null)
  const [exportStatus, setExportStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)

  const filteredNodes = getFilteredNodes()
  const totalNodes = Object.keys(nodes).length
  const filteredCount = Object.keys(filteredNodes).length
  const hasFilters = filteredCount !== totalNodes

  const handleExport = async (type: string, action: () => Promise<void> | void) => {
    setIsExporting(type)
    setExportStatus(null)
    
    try {
      await action()
      setExportStatus({ type: 'success', message: `${type} exported successfully!` })
      
      // Clear success message after 3 seconds
      setTimeout(() => setExportStatus(null), 3000)
    } catch (error) {
      console.error(`Export failed:`, error)
      setExportStatus({ 
        type: 'error', 
        message: `Failed to export ${type}. Please try again.` 
      })
    } finally {
      setIsExporting(null)
    }
  }

  const exportOptions = [
    {
      id: 'graph-png',
      title: 'Graph as PNG',
      description: 'Save current graph view as high-quality image',
      icon: <Camera className="w-5 h-5" />,
      action: () => exportGraphAsImage('png'),
      disabled: totalNodes === 0
    },
    {
      id: 'graph-svg',
      title: 'Graph as SVG',
      description: 'Save graph as scalable vector image',
      icon: <Image className="w-5 h-5" />,
      action: () => exportGraphAsImage('svg'),
      disabled: totalNodes === 0
    },
    {
      id: 'data-json',
      title: hasFilters ? 'Filtered Data (JSON)' : 'All Data (JSON)',
      description: `Export ${hasFilters ? filteredCount : totalNodes} nodes as JSON for analysis`,
      icon: <Database className="w-5 h-5" />,
      action: () => exportNodesAsJSON(
        hasFilters ? filteredNodes : nodes,
        hasFilters ? `filtered-task-data-${Date.now()}.json` : undefined
      ),
      disabled: (hasFilters ? filteredCount : totalNodes) === 0
    },
    {
      id: 'data-csv',
      title: hasFilters ? 'Filtered Data (CSV)' : 'All Data (CSV)',
      description: `Export ${hasFilters ? filteredCount : totalNodes} nodes as spreadsheet`,
      icon: <FileSpreadsheet className="w-5 h-5" />,
      action: () => exportNodesAsCSV(
        hasFilters ? filteredNodes : nodes,
        hasFilters ? `filtered-task-data-${Date.now()}.csv` : undefined
      ),
      disabled: (hasFilters ? filteredCount : totalNodes) === 0
    },
    {
      id: 'results',
      title: 'Task Results',
      description: `Download individual result files from ${hasFilters ? filteredCount : totalNodes} nodes`,
      icon: <Archive className="w-5 h-5" />,
      action: () => {
        const nodesToExport = Object.values(hasFilters ? filteredNodes : nodes)
          .filter(node => node.full_result || node.output_summary)
        exportNodeResults(nodesToExport, 'individual')
      },
      disabled: (() => {
        const nodesToExport = Object.values(hasFilters ? filteredNodes : nodes)
          .filter(node => node.full_result || node.output_summary)
        return nodesToExport.length === 0
      })()
    },
    {
      id: 'report-md',
      title: 'Project Report (Markdown)',
      description: 'Generate comprehensive project summary',
      icon: <FileText className="w-5 h-5" />,
      action: () => exportProjectReport(nodes, overallProjectGoal, 'markdown'),
      disabled: totalNodes === 0
    },
    {
      id: 'report-html',
      title: 'Project Report (HTML)',
      description: 'Generate interactive project report',
      icon: <FileText className="w-5 h-5" />,
      action: () => exportProjectReport(nodes, overallProjectGoal, 'html'),
      disabled: totalNodes === 0
    }
  ]

  return (
    <>
      {/* Desktop Export Button */}
      <div className="hidden md:block">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setIsOpen(true)}
          disabled={totalNodes === 0}
        >
          <Download className="w-4 h-4 mr-2" />
          Export
          {hasFilters && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5 text-xs">
              {filteredCount}
            </Badge>
          )}
        </Button>
      </div>

      {/* Mobile Export Button */}
      <div className="md:hidden">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setIsOpen(true)}
          disabled={totalNodes === 0}
          className="w-full justify-start text-xs"
        >
          <Download className="w-4 h-4 mr-2" />
          Export
          {hasFilters && (
            <Badge variant="secondary" className="ml-2 h-5 px-1.5 text-xs">
              {filteredCount}
            </Badge>
          )}
        </Button>
      </div>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Export Options</DialogTitle>
            <DialogDescription>
              Choose how to export your project data and visualizations.
              {hasFilters && (
                <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded-md text-sm">
                  <strong>Note:</strong> Some exports will include only the {filteredCount} filtered nodes.
                </div>
              )}
            </DialogDescription>
          </DialogHeader>

          {/* Export Status */}
          {exportStatus && (
            <div className={`flex items-center space-x-2 p-3 rounded-md ${
              exportStatus.type === 'success' 
                ? 'bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-200' 
                : 'bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200'
            }`}>
              {exportStatus.type === 'success' ? 
                <CheckCircle className="w-4 h-4" /> : 
                <AlertCircle className="w-4 h-4" />
              }
              <span className="text-sm">{exportStatus.message}</span>
            </div>
          )}

          {/* Export Options Grid */}
          <div className="flex-1 overflow-y-auto">
            <div className="grid grid-cols-1 gap-3">
              {exportOptions.map((option) => (
                <div
                  key={option.id}
                  className={`border rounded-lg p-4 transition-colors ${
                    option.disabled 
                      ? 'bg-muted/30 opacity-60' 
                      : 'hover:bg-muted/50 cursor-pointer'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start space-x-3 flex-1">
                      <div className="text-muted-foreground mt-1">
                        {option.icon}
                      </div>
                      <div className="flex-1">
                        <h4 className="font-medium text-sm">{option.title}</h4>
                        <p className="text-xs text-muted-foreground mt-1">
                          {option.description}
                        </p>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => handleExport(option.title, option.action)}
                      disabled={option.disabled || isExporting === option.title}
                      className="ml-3"
                    >
                      {isExporting === option.title ? (
                        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="border-t pt-4">
            <div className="flex items-center justify-between">
              <div className="text-xs text-muted-foreground">
                {totalNodes} total nodes • {filteredCount} currently shown
              </div>
              <Button variant="outline" onClick={() => setIsOpen(false)}>
                Close
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default ExportPanel 