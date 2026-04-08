"use client";

import { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  RefreshCw,
  XCircle,
  Zap,
} from "lucide-react";
import { fetchStatus } from "@/lib/api";
import { useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";

function formatLastUpdated(timestamp: number | null) {
  if (!timestamp) {
    return "尚未同步";
  }

  const deltaSeconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (deltaSeconds < 5) {
    return "刚刚同步";
  }
  if (deltaSeconds < 60) {
    return `${deltaSeconds} 秒前同步`;
  }

  const deltaMinutes = Math.round(deltaSeconds / 60);
  return `${deltaMinutes} 分钟前同步`;
}

export function StatusPanel() {
  const { status, setStatus, sources } = useCrawlerStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const getSourceName = (id: string) =>
    sources.find((s) => s.id === id)?.name ?? id;

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const nextStatus = await fetchStatus();
        if (cancelled) {
          return;
        }
        setStatus(nextStatus);
        setSyncError(null);
        setLastUpdatedAt(Date.now());
      } catch (error) {
        if (cancelled) {
          return;
        }
        setSyncError(
          error instanceof Error ? error.message : "状态同步失败，请稍后重试",
        );
      } finally {
        if (!cancelled) {
          setIsInitialLoading(false);
        }
      }
    };

    void poll();
    intervalRef.current = setInterval(() => {
      void poll();
    }, 2000);

    return () => {
      cancelled = true;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [setStatus]);

  const hasActivity =
    status.is_running ||
    status.completed_sources.length > 0 ||
    status.failed_sources.length > 0;
  const pct = Math.min(100, Math.max(0, Math.round(status.progress * 100)));

  const stateLabel = isInitialLoading
    ? "同步中"
    : status.is_running
      ? "爬取中"
      : hasActivity
        ? "本轮已结束"
        : "等待执行";
  const stateTone = isInitialLoading
    ? "text-amber-600 dark:text-amber-300"
    : status.is_running
      ? "text-blue-500"
      : hasActivity
        ? "text-emerald-500"
        : "text-muted-foreground";
  const stateDot = isInitialLoading
    ? "bg-amber-500 animate-pulse"
    : status.is_running
      ? "bg-blue-500 animate-pulse"
      : hasActivity
        ? "bg-emerald-500"
        : "bg-muted-foreground/40";

  const activityRows = [
    ...status.completed_sources.map((id) => ({ id, tone: "done" as const })),
    ...(status.current_source
      ? [{ id: status.current_source, tone: "running" as const }]
      : []),
    ...status.failed_sources.map((id) => ({ id, tone: "failed" as const })),
  ];

  return (
    <section className="overflow-hidden rounded-2xl border bg-card/90 shadow-sm backdrop-blur-sm">
      <div className="flex flex-col gap-3 border-b bg-muted/20 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
            Runtime Status
          </p>
          <h2 className="mt-2 text-lg font-semibold tracking-tight">实时状态</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            当前执行状态、进度与信源级别反馈
          </p>
        </div>
        <div className="space-y-1 text-right">
          <div className="flex items-center justify-end gap-1.5">
            <span className={cn("h-2 w-2 rounded-full", stateDot)} />
            <span className={cn("text-sm font-semibold", stateTone)}>
              {stateLabel}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {formatLastUpdated(lastUpdatedAt)}
          </p>
        </div>
      </div>

      {syncError && (
        <div className="border-b border-amber-500/20 bg-amber-500/10 px-5 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-300" />
            <div className="space-y-1">
              <p className="text-xs font-semibold text-amber-700 dark:text-amber-200">
                状态同步失败
              </p>
              <p className="text-xs text-amber-700/90 dark:text-amber-100/90">
                {syncError}。当前界面展示的是最近一次成功同步到的数据。
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-3 p-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border bg-background/80 p-4">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="h-3.5 w-3.5 shrink-0" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              当前信源
            </span>
          </div>
          <div className="mt-3 text-sm font-semibold">
            {status.current_source ? (
              <span className="text-blue-500">
                {getSourceName(status.current_source)}
              </span>
            ) : isInitialLoading ? (
              <span className="text-muted-foreground">同步中…</span>
            ) : (
              <span className="text-muted-foreground/70">暂无执行中的信源</span>
            )}
          </div>
        </div>

        <div className="rounded-xl border bg-emerald-500/5 p-4">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              已完成
            </span>
          </div>
          <div
            className={cn(
              "mt-3 text-3xl font-black leading-none tabular-nums",
              status.completed_sources.length > 0
                ? "text-emerald-500"
                : "text-muted-foreground/50",
            )}
          >
            {status.completed_sources.length}
          </div>
        </div>

        <div className="rounded-xl border bg-destructive/5 p-4">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              失败
            </span>
          </div>
          <div
            className={cn(
              "mt-3 text-3xl font-black leading-none tabular-nums",
              status.failed_sources.length > 0
                ? "text-destructive"
                : "text-muted-foreground/50",
            )}
          >
            {status.failed_sources.length}
          </div>
        </div>

        <div className="rounded-xl border bg-primary/5 p-4">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Zap className="h-3.5 w-3.5 shrink-0 text-primary" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              获取条目
            </span>
          </div>
          <div
            className={cn(
              "mt-3 text-3xl font-black leading-none tabular-nums",
              status.total_items > 0 ? "text-foreground" : "text-muted-foreground/50",
            )}
          >
            {status.total_items.toLocaleString()}
          </div>
        </div>
      </div>

      <div className="space-y-3 border-t border-border/40 px-5 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-muted-foreground">整体进度</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {status.is_running
                ? "系统正在轮询当前任务状态"
                : hasActivity
                  ? "本轮执行已结束，可查看右侧结果区"
                  : "尚未开始执行"}
            </p>
          </div>
          <span className="text-sm font-bold tabular-nums">{pct}%</span>
        </div>
        <div className="relative h-3 overflow-hidden rounded-full bg-muted/40">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 ease-out",
              status.is_running
                ? "bg-gradient-to-r from-blue-500 to-cyan-400"
                : hasActivity
                  ? "bg-gradient-to-r from-emerald-500 to-emerald-400"
                  : "bg-muted",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {activityRows.length > 0 ? (
        <div className="border-t border-border/40 px-5 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                信源反馈
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                已经返回过结果的信源会优先显示在这里
              </p>
            </div>
            {status.is_running && (
              <div className="flex items-center gap-1.5 text-xs text-blue-500">
                <RefreshCw className="h-3 w-3 animate-spin" />
                每 2 秒刷新
              </div>
            )}
          </div>
          <div className="max-h-60 overflow-y-auto rounded-xl border border-border/50 scrollbar-thin">
            {activityRows.map(({ id, tone }) => (
              <div
                key={`${tone}-${id}`}
                className={cn(
                  "flex items-center gap-2.5 border-b border-border/40 px-3 py-2.5 last:border-b-0",
                  tone === "done" && "bg-emerald-500/5",
                  tone === "running" && "bg-blue-500/10",
                  tone === "failed" && "bg-destructive/5",
                )}
              >
                {tone === "done" ? (
                  <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                ) : tone === "running" ? (
                  <Activity className="h-3.5 w-3.5 shrink-0 text-blue-500" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
                )}
                <span className="flex-1 truncate text-xs text-foreground/85">
                  {getSourceName(id)}
                </span>
                <span
                  className={cn(
                    "text-[10px] font-semibold",
                    tone === "done" && "text-emerald-500",
                    tone === "running" && "text-blue-500",
                    tone === "failed" && "text-destructive",
                  )}
                >
                  {tone === "done" ? "完成" : tone === "running" ? "进行中" : "失败"}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="border-t border-border/40 px-5 py-4">
          <div className="rounded-xl border border-dashed bg-background/70 px-4 py-5">
            <p className="text-sm font-medium">
              {isInitialLoading
                ? "正在同步当前系统状态…"
                : "还没有可展示的运行反馈"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              在左侧选择信源，配置执行参数后点击“开始爬取”。
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
