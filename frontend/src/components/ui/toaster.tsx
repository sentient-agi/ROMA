import React from "react";
import { useToast } from "@/components/ui/use-toast";
import { cn } from "@/lib/utils";

export const Toaster: React.FC = () => {
  const { toasts } = useToast();

  return (
    <div className="fixed md:top-4 bottom-4 right-4 z-50 space-y-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            "rounded-lg border p-4 shadow-lg max-w-sm animate-in slide-in-from-top-2",
            toast.variant === "destructive"
              ? "bg-destructive text-destructive-foreground border-destructive"
              : "bg-background text-foreground border-border",
          )}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              {toast.title && (
                <div className="font-semibold text-sm">{toast.title}</div>
              )}
              {toast.description && (
                <div className="text-sm opacity-90 mt-1">
                  {toast.description}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
};

