"use client";

import { useEffect, useState } from "react";
import { FileText, Landmark, Radar, Sparkles } from "lucide-react";
import {
  fetchLatestSentimentReport,
  fetchLeadershipAll,
  fetchReportDimensions,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  ReportDimensionsResponse,
  ReportResponse,
  UniversityLeadershipAllResponse,
} from "@/types";

type IntelligenceState = {
  dimensions: ReportDimensionsResponse | null;
  report: ReportResponse | null;
  leadership: UniversityLeadershipAllResponse | null;
};

function stripMarkdown(content: string) {
  return content.replace(/[#>*_`-]/g, " ").replace(/\s+/g, " ").trim();
}

export function IntelligencePanel() {
  const [state, setState] = useState<IntelligenceState>({
    dimensions: null,
    report: null,
    leadership: null,
  });

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const [dimensions, report, leadership] = await Promise.allSettled([
        fetchReportDimensions(),
        fetchLatestSentimentReport(),
        fetchLeadershipAll(),
      ]);

      if (cancelled) {
        return;
      }

      setState({
        dimensions: dimensions.status === "fulfilled" ? dimensions.value : null,
        report: report.status === "fulfilled" ? report.value : null,
        leadership: leadership.status === "fulfilled" ? leadership.value : null,
      });
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const reportPreview = state.report?.content
    ? stripMarkdown(state.report.content).slice(0, 220)
    : null;
  const leadershipPreview = state.leadership?.items.slice(0, 4) ?? [];

  return (
    <section className="rounded-xl border bg-card overflow-hidden">
      <div className="flex items-center gap-2.5 border-b bg-muted/20 px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/10">
          <Sparkles className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h2 className="text-sm font-semibold">智能分析面板</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            报告能力、舆情快照与高校领导增量预览
          </p>
        </div>
      </div>

      <div className="space-y-4 p-5">
        <div className="rounded-xl border bg-background/70 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Radar className="h-4 w-4 text-blue-500" />
            <h3 className="text-sm font-semibold">报告维度状态</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {state.dimensions?.dimensions.length ? (
              state.dimensions.dimensions.map((item) => (
                <Badge
                  key={item.id}
                  variant="outline"
                  className={cn(
                    "h-6 px-2.5 text-[11px]",
                    item.status === "implemented"
                      ? "border-emerald-300 bg-emerald-500/10 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300"
                      : "border-amber-300 bg-amber-500/10 text-amber-700 dark:border-amber-800 dark:text-amber-300",
                  )}
                >
                  {item.name}
                </Badge>
              ))
            ) : (
              <p className="text-xs text-muted-foreground">报告能力尚未连通。</p>
            )}
          </div>
        </div>

        <div className="rounded-xl border bg-background/70 p-4">
          <div className="mb-3 flex items-center gap-2">
            <FileText className="h-4 w-4 text-emerald-500" />
            <h3 className="text-sm font-semibold">最近 7 天舆情报告</h3>
          </div>

          {state.report ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                <span>{state.report.metadata.title}</span>
                <span>·</span>
                <span>{state.report.metadata.total_items} 条样本</span>
              </div>
              <p className="text-sm leading-6 text-foreground/85">
                {reportPreview || "报告已生成，但暂无摘要内容。"}
                {reportPreview && "..."}
              </p>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              暂无可展示的舆情报告，可能需要先完成数据抓取或报告生成。
            </p>
          )}
        </div>

        <div className="rounded-xl border bg-background/70 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Landmark className="h-4 w-4 text-rose-500" />
            <h3 className="text-sm font-semibold">高校领导样本</h3>
          </div>

          {leadershipPreview.length > 0 ? (
            <div className="space-y-2">
              {leadershipPreview.map((item) => (
                <div
                  key={item.source_id}
                  className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {item.university_name}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      {item.group || item.source_name || "领导信源"}
                    </p>
                  </div>
                  <Badge variant="secondary" className="shrink-0">
                    {item.leader_count} 人
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              高校领导爬虫尚未产出预览样本。
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
