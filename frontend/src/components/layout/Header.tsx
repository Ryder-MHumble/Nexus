"use client";

import { useEffect, useState } from "react";
import { Webhook } from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";
import { checkHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Header() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const check = async () => setOnline(await checkHealth());
    check();
    const t = setInterval(check, 10000);
    return () => clearInterval(t);
  }, []);

  return (
    <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 sticky top-0 z-50">
      <div className="flex h-14 items-center px-6 gap-4">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Webhook className="h-4 w-4" />
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-none">
              Crawler Controller
            </h1>
            <p className="text-xs text-muted-foreground leading-none mt-0.5">
              信息爬虫控制台
            </p>
          </div>
        </div>

        <div className="flex-1" />

        {/* API Status */}
        <div className="flex items-center gap-1.5 text-xs">
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
        </div>

        <ThemeToggle />
      </div>
    </header>
  );
}
