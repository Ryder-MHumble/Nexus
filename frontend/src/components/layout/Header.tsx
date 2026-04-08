"use client";

import { useEffect, useState } from "react";
import { Webhook } from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";
import { checkHealth } from "@/lib/api";
import { useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function Header() {
  const [online, setOnline] = useState<boolean | null>(null);
  const { selectedIds, status } = useCrawlerStore();

  useEffect(() => {
    const check = async () => setOnline(await checkHealth());
    check();
    const t = setInterval(check, 10000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
      <div className="mx-auto flex min-h-16 max-w-[1680px] flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Webhook className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-none">Nexus Console</h1>
            <p className="text-xs text-muted-foreground leading-none mt-0.5">
              增量爬虫与知识能力控制台
            </p>
          </div>
        </div>

        <div className="ml-auto hidden items-center gap-2 lg:flex">
          <span className="rounded-full border bg-muted/40 px-3 py-1 text-[11px] font-medium text-muted-foreground">
            已选 {selectedIds.size}
          </span>
          <span
            className={cn(
              "rounded-full border px-3 py-1 text-[11px] font-medium",
              status.is_running
                ? "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-300"
                : "border-border/80 bg-muted/40 text-muted-foreground",
            )}
          >
            {status.is_running ? "任务运行中" : "任务待执行"}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-xs" aria-live="polite">
          <span
            className={cn(
              "inline-block h-2 w-2 rounded-full",
              online === null
                ? "bg-muted-foreground animate-pulse"
                : online
                  ? "bg-emerald-500"
                  : "bg-destructive",
            )}
          />
          <span className="text-muted-foreground hidden sm:inline">
            {online === null ? "检测中…" : online ? "API 已连接" : "API 未连接"}
          </span>
          <span className="sr-only">
            {online === null ? "API connection checking" : online ? "API online" : "API offline"}
          </span>
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
