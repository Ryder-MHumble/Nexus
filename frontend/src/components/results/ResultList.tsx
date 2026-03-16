"use client";

import { CheckCircle2, Download, FileText, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function ResultList() {
  const { status, exportFormat, sources, downloadResult } = useCrawlerStore();

  const isDone =
    !status.is_running &&
    (status.completed_sources.length > 0 || status.failed_sources.length > 0);

  if (!isDone) return null;

  const getSourceName = (id: string) =>
    sources.find((s) => s.id === id)?.name ?? id;

  const allResults = [
    ...status.completed_sources.map((id) => ({ id, ok: true })),
    ...status.failed_sources.map((id) => ({ id, ok: false })),
  ];

  const successRate =
    allResults.length > 0
      ? Math.round((status.completed_sources.length / allResults.length) * 100)
      : 0;

  return (
    <div className="rounded-xl border bg-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b bg-muted/20 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 shrink-0">
            <FileText className="h-3.5 w-3.5 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-semibold">爬取结果</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              成功{" "}
              <span className="text-emerald-500 font-bold">
                {status.completed_sources.length}
              </span>{" "}
              个信源，共获取{" "}
              <span className="text-foreground font-bold">
                {status.total_items.toLocaleString()}
              </span>{" "}
              条数据
              {status.failed_sources.length > 0 && (
                <>
                  ，失败{" "}
                  <span className="text-destructive font-bold">
                    {status.failed_sources.length}
                  </span>{" "}
                  个
                </>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Success rate badge */}
          <Badge
            variant="outline"
            className={cn(
              "text-xs font-semibold",
              successRate === 100
                ? "text-emerald-600 border-emerald-300 dark:text-emerald-400 dark:border-emerald-700"
                : successRate >= 50
                  ? "text-amber-600 border-amber-300 dark:text-amber-400 dark:border-amber-700"
                  : "text-destructive border-destructive/40",
            )}
          >
            成功率 {successRate}%
          </Badge>

          {exportFormat !== "database" && status.total_items > 0 && (
            <Button
              onClick={downloadResult}
              size="sm"
              className="gap-2 h-8 text-xs font-semibold"
            >
              <Download className="h-3.5 w-3.5" />
              下载 {exportFormat.toUpperCase()}
            </Button>
          )}
          {exportFormat === "database" && status.total_items > 0 && (
            <Badge
              variant="outline"
              className="text-emerald-600 border-emerald-300 dark:text-emerald-400 dark:border-emerald-700"
            >
              ✓ 已存入数据库
            </Badge>
          )}
        </div>
      </div>

      {/* Result list */}
      <div className="divide-y divide-border/40 overflow-y-auto scrollbar-hide max-h-64">
        {allResults.map(({ id, ok }) => (
          <div
            key={id}
            className={cn(
              "flex items-center gap-3 px-5 py-2.5",
              ok ? "hover:bg-emerald-500/5" : "hover:bg-destructive/5",
              "transition-colors",
            )}
          >
            {ok ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
            ) : (
              <XCircle className="h-4 w-4 text-destructive shrink-0" />
            )}
            <span className="flex-1 truncate text-sm text-foreground/80">
              {getSourceName(id)}
            </span>
            <Badge
              variant={ok ? "outline" : "destructive"}
              className={cn(
                "text-[10px] h-5 shrink-0 font-semibold",
                ok &&
                  "text-emerald-600 border-emerald-300 dark:text-emerald-400 dark:border-emerald-800 bg-emerald-500/5",
              )}
            >
              {ok ? "成功" : "失败"}
            </Badge>
          </div>
        ))}
      </div>
    </div>
  );
}
