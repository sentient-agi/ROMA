import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Brain, Download, Eye, EyeOff, Menu } from "lucide-react";
import { useTaskGraphStore } from "@/stores/taskGraphStore";
import ThemeToggle from "@/components/theme/ThemeToggle";
import FilterPanel from "@/components/panels/FilterPanel";
import ExportPanel from "@/components/panels/ExportPanel";
import ContextFlowPanel from "@/components/panels/ContextFlowPanel";
import ProjectSidebar from "@/components/sidebar/ProjectSidebar";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { exportProjectReport } from "@/lib/exportUtils";
import { Separator } from "@/components/ui/separator";

const Header: React.FC = () => {
  const { showContextFlow, toggleContextFlow, nodes, overallProjectGoal } =
    useTaskGraphStore();

  const hasNodes = Object.keys(nodes).length > 0;
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const handleDownloadReport = async () => {
    try {
      // Use the existing export functionality to download as markdown
      exportProjectReport(nodes, overallProjectGoal, "markdown");
    } catch (error) {
      console.error("Failed to download report:", error);
    }
  };

  return (
    <header className="border-b bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50 shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 md:px-6">
        {/* Logo and Title */}
        <div className="flex items-center space-x-2 md:space-x-3">
          {/* Mobile Sidebar Toggle - Hidden since sidebar is in menubar */}
          <div className="md:hidden">
            {/* This button is hidden since sidebar content is now in the menubar */}
          </div>

          <div className="flex items-center justify-center w-8 h-8 rounded-lg">
            <Brain className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base md:text-md font-semibold">
              Sentient Research Agent
            </h2>
          </div>
        </div>

        {/* Desktop Menu */}
        <div className="hidden md:flex items-center space-x-2">
          {hasNodes && (
            <>
              {/* Context Flow Toggle */}
              <Button
                variant="outline"
                size="sm"
                onClick={toggleContextFlow}
                className="h-8"
              >
                {showContextFlow ? (
                  <>
                    <EyeOff className="w-4 h-4 mr-2" />
                    Hide Context Flow
                  </>
                ) : (
                  <>
                    <Eye className="w-4 h-4 mr-2" />
                    Show Context Flow
                  </>
                )}
              </Button>

              {/* Download Report */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownloadReport}
                className="h-8"
              >
                <Download className="w-4 h-4 mr-2" />
                Download Report
              </Button>

              {/* Desktop Filter, Export, and Context Flow Panels */}
              <div className="flex items-center space-x-2 border-l pl-2 ml-2">
                <div className="text-xs text-muted-foreground">Filter:</div>
                <FilterPanel />

                <div className="text-xs text-muted-foreground ml-2">
                  Export:
                </div>
                <ExportPanel />

                <div className="text-xs text-muted-foreground ml-2">
                  Context Flow:
                </div>
                <ContextFlowPanel />
              </div>
            </>
          )}

          {/* Theme Toggle */}
          <ThemeToggle />
        </div>
        {/* Mobile Menu */}
        <div className="md:hidden">
          <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="w-full sm:w-80 p-0">
              <div className="flex flex-col h-full">
                <div className="p-6 border-b">
                  <div className="flex items-center justify-between">
                    <SheetTitle className="text-xl">Menu</SheetTitle>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                  {/* Projects Section */}
                  <div>
                    <ProjectSidebar
                      forceMobileExpanded={true}
                      onProjectSelect={() => {
                        console.log("Project selected, closing mobile menu");
                        setMobileMenuOpen(false);
                      }}
                    />
                  </div>

                  {hasNodes && (
                    <>
                      <Separator />
                      {/* Filter and Export Panels - 2 Column Grid */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-sm font-medium mb-2 block">
                            Filter
                          </label>
                          <FilterPanel />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-2 block">
                            Export
                          </label>
                          <ExportPanel />
                        </div>
                      </div>

                      {/* Context Flow Panel */}
                      <div>
                        <label className="text-sm font-medium mb-2 block">
                          Context Flow
                        </label>
                        <ContextFlowPanel />
                      </div>

                      {/* Context Flow Toggle and Download Report - 2 Column Grid */}
                      <div className="grid grid-cols-2 gap-3">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            toggleContextFlow();
                            setMobileMenuOpen(false);
                          }}
                          className="justify-start text-xs"
                        >
                          {showContextFlow ? (
                            <>
                              <EyeOff className="w-4 h-4 mr-2" />
                              Hide Context Flow
                            </>
                          ) : (
                            <>
                              <Eye className="w-4 h-4 mr-2" />
                              Show Context Flow
                            </>
                          )}
                        </Button>

                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            handleDownloadReport();
                            setMobileMenuOpen(false);
                          }}
                          className="justify-start text-xs"
                        >
                          <Download className="w-4 h-4 mr-2" />
                          Download Report
                        </Button>
                      </div>
                    </>
                  )}

                  {/* Theme Toggle */}
                  <div className="pt-4 border-t">
                    <label className="text-sm font-medium mb-2 block">
                      Theme
                    </label>
                    <ThemeToggle />
                  </div>
                </div>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
};

export default Header;
