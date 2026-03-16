"use client";

import { useEffect, useRef } from "react";
import { Activity, CheckCircle2, Clock, XCircle, Zap } from "lucide-react";
import { fetchStatus } from "@/lib/api";
import { useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function StatusPanel() {
  const { status, setStatus, sources } = useCrawlerStore();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const getSourceName = (id: string) =>
    sources.find((s) => s.id === id)?.name ?? id;

  useEffect(() => {
    const poll = async () => {
      try {
        setStatus(await fetchStatus());
      } catch {
        /* ignore */
      }
    };
    poll();
    intervalRef.current = setInterval(poll, 2000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [setStatus]);

  const hasActivity =
    status.is_running ||
    status.completed_sources.length > 0 ||
    status.failed_sources.length > 0;

  const pct = Math.round(status.progress * 100);

  const stateLabel = status.is_running
    ? "爬取中…"
    : hasActivity
      ? "已完成"
      : "就绪";
  const stateColor = status.is_running
    ? "text-blue-500"
    : hasActivity
      ? "text-emerald-500"
      : "text-muted-foreground";
  const dotColor = status.is_running
    ? "bg-blue-500 animate-pulse"
    : hasActivity
      ? "bg-emerald-500"
      : "bg-muted-foreground/40";

  return (
    <div className="rounded-xl border bg-card overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-2.5 px-5 py-3.5 border-b bg-muted/20">
        <div
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-lg shrink-0",
            status.is_running
              ? "bg-blue-500/15"
              : hasActivity
                ? "bg-emerald-500/10"
                : "bg-muted",
          )}
        >
          <Activity
            className={cn(
              "h-3.5 w-3.5",
              status.is_running
                ? "text-blue-500 animate-pulse"
                : hasActivity
                  ? "text-emerald-500"
                  : "text-muted-foreground",
            )}
          />
        </div>
        <h2 className="text-sm font-semibold">实时状态</h2>
        <div className="ml-auto flex items-center gap-1.5">
          <span className={cn("h-2 w-2 rounded-full", dotColor)} />
          <span className={cn("text-xs font-semibold", stateColor)}>
            {stateLabel}
          </span>
        </div>
      </div>

      {/* ── Stat row — 4 equal columns with card styling ─────────────────────────── */}
      <div className="p-4 grid grid-cols-4 gap-3">
        {/* Current source */}
        <div className="flex flex-col gap-2 p-3 rounded-lg border bg-muted/10">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Clock className="h-3.5 w-3.5 shrink-0" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              当前信源
            </span>
          </div>
          <div className="text-sm font-semibold truncate min-w-0">
            {status.current_source ? (
              <span className="text-blue-500">
                {getSourceName(status.current_source)}
              </span>
            ) : (
              <span className="text-muted-foreground/60">—</span>
            )}
          </div>
        </div>

        {/* Completed */}
        <div className="flex flex-col gap-2 p-3 rounded-lg border bg-emerald-500/5">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              已完成
            </span>
          </div>
          <span
            className={cn(
              "text-2xl font-black tabular-nums leading-none",
              status.completed_sources.length > 0
                ? "text-emerald-500"
                : "text-muted-foreground/50",
            )}
          >
            {status.completed_sources.length}
          </span>
        </div>

        {/* Failed */}
        <div className="flex flex-col gap-2 p-3 rounded-lg border bg-destructive/5">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              失败
            </span>
          </div>
          <span
            className={cn(
              "text-2xl font-black tabular-nums leading-none",
              status.failed_sources.length > 0
                ? "text-destructive"
                : "text-muted-foreground/50",
            )}
          >
            {status.failed_sources.length}
          </span>
        </div>

        {/* Total items */}
        <div className="flex flex-col gap-2 p-3 rounded-lg border bg-primary/5">
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <Zap className="h-3.5 w-3.5 text-primary shrink-0" />
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              获取条目
            </span>
          </div>
          <span
            className={cn(
              "text-2xl font-black tabular-nums leading-none",
              status.total_items > 0
                ? "text-foreground"
                : "text-muted-foreground/50",
            )}
          >
            {status.total_items > 0 ? status.total_items.toLocaleString() : "0"}
          </span>
        </div>
      </div>

      {/* ── Progress bar with gradient ────────────────────────────────────────── */}
      <div className="px-5 py-4 space-y-2.5 border-t border-border/40">
        <div className="flex justify-between items-center">
          <span className="text-xs text-muted-foreground font-medium">
            整体进度
          </span>
          <span className="text-sm font-bold tabular-nums">{pct}%</span>
        </div>
        <div className="relative h-3 rounded-full bg-muted/40 overflow-hidden">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 ease-out",
              status.is_running
                ? "bg-gradient-to-r from-blue-500 to-blue-400"
                : hasActivity
                  ? "bg-gradient-to-r from-emerald-500 to-emerald-400"
                  : "bg-muted",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* ── Live source list (running) / Idle hint ──────────────── */}
      {status.is_running ? (
        <div className="px-5 py-4 space-y-2 border-t border-border/40">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            信源进度
          </p>
          <div className="rounded-lg border border-border/50 divide-y divide-border/30 overflow-hidden max-h-48 overflow-y-auto scrollbar-hide">
            {status.completed_sources.map((id) => (
              <div
                key={id}
                className="flex items-center gap-2.5 px-3 py-2 bg-emerald-500/5"
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                <span className="text-xs truncate flex-1 text-foreground/80">
                  {getSourceName(id)}
                </span>
                <span className="text-[10px] text-emerald-500 font-semibold shrink-0">
                  完成
                </span>
              </div>
            ))}
            {status.current_source && (
              <div className="flex items-center gap-2.5 px-3 py-2 bg-blue-500/10">
                <span className="h-3.5 w-3.5 shrink-0 flex items-center justify-center">
                  <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                </span>
                <span className="text-xs font-semibold text-blue-500 truncate flex-1">
                  {getSourceName(status.current_source)}
                </span>
                <span className="text-[10px] text-blue-500 font-semibold shrink-0">
                  进行中
                </span>
              </div>
            )}
            {status.failed_sources.map((id) => (
              <div
                key={id}
                className="flex items-center gap-2.5 px-3 py-2 bg-destructive/5"
              >
                <XCircle className="h-3.5 w-3.5 text-destructive shrink-0" />
                <span className="text-xs truncate flex-1 text-foreground/80">
                  {getSourceName(id)}
                </span>
                <span className="text-[10px] text-destructive font-semibold shrink-0">
                  失败
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : !hasActivity ? (
        <div className="px-5 py-4 border-t border-border/40">
          <p className="text-xs text-muted-foreground">
            在左侧选择信源，配置过滤条件后点击「开始爬取」
          </p>
        </div>
      ) : null}
    </div>
  );
}
