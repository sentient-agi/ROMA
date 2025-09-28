import React, { useEffect, useState, useMemo } from "react";
import { useTaskGraphStore } from "@/stores/taskGraphStore";
import { useProjectStore } from "@/stores/projectStore";
import Header from "./Header";
import ProjectSidebar from "@/components/sidebar/ProjectSidebar";
import GraphVisualization from "@/components/graph/GraphVisualization";
import NodeDetailsPanel from "@/components/panels/NodeDetailsPanel";
import ComparisonPanel from "@/components/panels/ComparisonPanel";
import MultiSelectToolbar from "@/components/panels/MultiSelectToolbar";
import ProjectInput from "@/components/project/ProjectInput";
import { HITLModal } from "@/components/hitl/HITLModal";
import ConnectionStatus from "@/components/status/ConnectionStatus";
import HITLLog from "@/components/hitl/HITLLog";
import HITLNotification from "@/components/hitl/HITLNotification";
import { wsManager } from "@/services/websocketManager";

const MainLayout: React.FC = () => {
  const {
    isConnected,
    nodes,
    overallProjectGoal,
    isHITLModalOpen,
    isLoading,
    selectedNodeIds,
    isComparisonPanelOpen,
  } = useTaskGraphStore();

  const { isSidebarOpen, getCurrentProject } = useProjectStore();

  const [loadingMessage, setLoadingMessage] = useState(
    "Initializing project...",
  );
  const [loadingDots, setLoadingDots] = useState("");

  // Initialize WebSocket connection through manager
  useEffect(() => {
    wsManager.initialize();
  }, []);

  // Handle connection status changes
  useEffect(() => {
    console.log("🔌 Connection status changed:", isConnected);
  }, [isConnected]);

  // Animated loading dots
  useEffect(() => {
    if (!isLoading) return;

    const interval = setInterval(() => {
      setLoadingDots((prev) => (prev.length >= 3 ? "" : prev + "."));
    }, 500);

    return () => clearInterval(interval);
  }, [isLoading]);

  // Update loading message based on time elapsed
  useEffect(() => {
    if (!isLoading) return;

    const messages = [
      "Initializing project...",
      "Setting up task framework...",
      "Creating root task...",
      "Planning task decomposition...",
      "Calling AI agents...",
      "Processing initial analysis...",
    ];

    let messageIndex = 0;
    setLoadingMessage(messages[0]);

    const interval = setInterval(() => {
      messageIndex = (messageIndex + 1) % messages.length;
      setLoadingMessage(messages[messageIndex]);
    }, 3000);

    return () => clearInterval(interval);
  }, [isLoading]);

  const hasNodes = Object.keys(nodes).length > 0;
  const hasMultipleSelected = selectedNodeIds.size > 1;
  const currentProject = getCurrentProject();

  // Memoize the debug object to prevent unnecessary re-renders
  const debugInfo = useMemo(
    () => ({
      hasNodes,
      nodeCount: Object.keys(nodes).length,
      isConnected,
      isLoading,
      currentProject: currentProject?.title,
    }),
    [
      hasNodes,
      Object.keys(nodes).length,
      isConnected,
      isLoading,
      currentProject,
    ],
  );

  // Only log when values actually change
  useEffect(() => {
    console.log("MainLayout render:", debugInfo);
  }, [debugInfo]);

  // Show ProjectInput when no current project or no nodes and not loading
  const showProjectInput = !currentProject || (!hasNodes && !isLoading);

  return (
    <div className="h-screen flex bg-background">
      {/* Sidebar - Hidden on mobile */}
      <div className="hidden md:block">
        <ProjectSidebar />
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />

        {/* Multi-Selection Toolbar */}
        {hasNodes && <MultiSelectToolbar />}

        <main className="flex-1 overflow-hidden">
          {showProjectInput ? (
            <div className="h-full overflow-y-auto">
              <ProjectInput />
            </div>
          ) : (
            <div className="h-full grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-4 p-4">
              <div className="h-full">
                {isLoading ? (
                  <div className="h-full flex items-center justify-center">
                    <div className="text-center animate-fade-in">
                      <div className="relative">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
                        <div className="absolute inset-0 rounded-full h-12 w-12 border-2 border-primary/20 mx-auto"></div>
                      </div>
                      <h3 className="text-lg font-medium mt-4">
                        {loadingMessage}
                        {loadingDots}
                      </h3>
                      <p className="text-muted-foreground mt-2">
                        {currentProject
                          ? `Working on: ${currentProject.title}`
                          : "Setting up your project..."}
                      </p>
                    </div>
                  </div>
                ) : (
                  <GraphVisualization />
                )}
              </div>
              <div className="h-full space-y-4 overflow-y-auto">
                {/* Project Goal Display */}
                {(overallProjectGoal || currentProject) && (
                  <div className="border-b bg-muted/30 px-6 py-4">
                    <div className="text-sm text-muted-foreground">
                      Current Project
                    </div>
                    <div className="text-lg font-medium">
                      {currentProject?.title || overallProjectGoal}
                    </div>
                    {currentProject?.description &&
                      currentProject.description !== currentProject.title && (
                        <div className="text-sm text-muted-foreground mt-1">
                          {currentProject.description}
                        </div>
                      )}
                  </div>
                )}

                {/* Comparison Panel (when multiple nodes selected) */}
                {isComparisonPanelOpen && hasMultipleSelected && (
                  <ComparisonPanel />
                )}

                {/* Node Details Panel (when single node selected) */}
                {!isComparisonPanelOpen && <NodeDetailsPanel />}
              </div>
            </div>
          )}
        </main>

        {/* Status Components */}
        <ConnectionStatus />

        {/* HITL Modal - Always render, it handles its own visibility */}
        <HITLModal />

        {/* Add HITL Log in a fixed position */}
        <div className="absolute top-4 right-4 z-10">
          <HITLLog />
        </div>

        {/* Add HITL Notification */}
        <HITLNotification />
      </div>
    </div>
  );
};

export default MainLayout;

