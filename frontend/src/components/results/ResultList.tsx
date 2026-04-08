"use client";

import {
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function ResultList() {
  const { status, exportFormat, sources, downloadResult } = useCrawlerStore();

  const getSourceName = (id: string) =>
    sources.find((source) => source.id === id)?.name ?? id;

  const finishedCount =
    status.completed_sources.length + status.failed_sources.length;
  const isDone = !status.is_running && finishedCount > 0;
  const allResults = [
    ...status.completed_sources.map((id) => ({
      id,
      state: "success" as const,
    })),
    ...(status.current_source
      ? [{ id: status.current_source, state: "running" as const }]
      : []),
    ...status.failed_sources.map((id) => ({
      id,
      state: "failed" as const,
    })),
  ];
  const hasResults = allResults.length > 0;

  const successRate =
    finishedCount > 0
      ? Math.round((status.completed_sources.length / finishedCount) * 100)
      : 0;
  const summaryText = status.is_running
    ? "任务执行中，完成和失败的信源会持续汇总到这里。"
    : isDone
      ? `成功 ${status.completed_sources.length} 个信源，共获取 ${status.total_items.toLocaleString()} 条数据${status.failed_sources.length > 0 ? `，失败 ${status.failed_sources.length} 个` : ""}`
      : "结果会在任务执行后按信源逐项展示，并在结束后开放导出。";

  return (
    <section className="overflow-hidden rounded-2xl border bg-card/90 shadow-sm backdrop-blur-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/20 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <FileText className="h-3.5 w-3.5 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-semibold">爬取结果</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">{summaryText}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {finishedCount > 0 && (
            <Badge
              variant="outline"
              className={cn(
                "text-xs font-semibold",
                successRate === 100
                  ? "border-emerald-300 text-emerald-600 dark:border-emerald-700 dark:text-emerald-400"
                  : successRate >= 50
                    ? "border-amber-300 text-amber-600 dark:border-amber-700 dark:text-amber-400"
                    : "border-destructive/40 text-destructive",
              )}
            >
              成功率 {successRate}%
            </Badge>
          )}

          {status.is_running && (
            <Badge variant="secondary" className="gap-1 text-xs">
              <Loader2 className="h-3 w-3 animate-spin" />
              汇总中
            </Badge>
          )}

          {isDone && exportFormat !== "database" && status.total_items > 0 && (
            <Button
              onClick={downloadResult}
              size="sm"
              className="h-8 gap-2 text-xs font-semibold"
            >
              <Download className="h-3.5 w-3.5" />
              下载 {exportFormat.toUpperCase()}
            </Button>
          )}

          {isDone && exportFormat === "database" && status.total_items > 0 && (
            <Badge
              variant="outline"
              className="border-emerald-300 text-emerald-600 dark:border-emerald-700 dark:text-emerald-400"
            >
              ✓ 已存入数据库
            </Badge>
          )}
        </div>
      </div>

      <div className="max-h-[22rem] overflow-y-auto">
        {hasResults ? (
          <div className="divide-y divide-border/40">
            {allResults.map(({ id, state }) => (
              <div
                key={`${state}-${id}`}
                className={cn(
                  "flex items-center gap-3 px-5 py-2.5 transition-colors",
                  state === "success" && "hover:bg-emerald-500/5",
                  state === "running" && "hover:bg-blue-500/5",
                  state === "failed" && "hover:bg-destructive/5",
                )}
              >
                {state === "success" ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                ) : state === "running" ? (
                  <Loader2 className="h-4 w-4 shrink-0 animate-spin text-blue-500" />
                ) : (
                  <XCircle className="h-4 w-4 shrink-0 text-destructive" />
                )}
                <span className="flex-1 truncate text-sm text-foreground/80">
                  {getSourceName(id)}
                </span>
                <Badge
                  variant={state === "failed" ? "destructive" : "outline"}
                  className={cn(
                    "h-5 shrink-0 text-[10px] font-semibold",
                    state === "success" &&
                      "border-emerald-300 bg-emerald-500/5 text-emerald-600 dark:border-emerald-800 dark:text-emerald-400",
                    state === "running" &&
                      "border-blue-300 bg-blue-500/5 text-blue-600 dark:border-blue-800 dark:text-blue-300",
                  )}
                >
                  {state === "success"
                    ? "成功"
                    : state === "running"
                      ? "进行中"
                      : "失败"}
                </Badge>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center px-5 py-10 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/50">
              <FileText className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="mt-4 text-sm font-medium">结果区暂时为空</p>
            <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">
              启动任务后，这里会持续展示成功、失败和进行中的信源结果。
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
