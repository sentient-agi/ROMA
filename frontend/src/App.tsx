import React from "react";
import { TaskGraphProvider } from "@/contexts/TaskGraphContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import MainLayout from "@/components/layout/MainLayout";
import { Toaster } from "@/components/ui/toaster";
import ErrorBoundary from "@/components/ErrorBoundary";

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark" storageKey="sentient-agent-theme">
        <TaskGraphProvider>
          <MainLayout />
          <Toaster />
        </TaskGraphProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;

