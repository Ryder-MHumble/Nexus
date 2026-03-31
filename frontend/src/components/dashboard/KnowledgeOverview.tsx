"use client";

import { useEffect, useState } from "react";
import {
  Building2,
  CalendarRange,
  FolderKanban,
  GraduationCap,
  Landmark,
  Sparkles,
} from "lucide-react";
import {
  fetchEventStats,
  fetchInstitutionStats,
  fetchLeadershipAll,
  fetchProjectStats,
  fetchReportDimensions,
  fetchScholarStats,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  CountBucket,
  EventStatsResponse,
  InstitutionStatsResponse,
  ProjectStatsResponse,
  ReportDimensionsResponse,
  ScholarStatsBucket,
  ScholarStatsResponse,
  UniversityLeadershipAllResponse,
} from "@/types";

type OverviewState = {
  institutions: InstitutionStatsResponse | null;
  scholars: ScholarStatsResponse | null;
  projects: ProjectStatsResponse | null;
  events: EventStatsResponse | null;
  leadership: UniversityLeadershipAllResponse | null;
  reports: ReportDimensionsResponse | null;
};

function toCountLabel(items?: CountBucket[] | ScholarStatsBucket[]) {
  const first = items?.[0];
  if (!first) {
    return "待生成统计";
  }

  const labelEntry = Object.entries(first).find(
    ([key, value]) => key !== "count" && typeof value === "string" && value,
  );
  const count = typeof first.count === "number" ? first.count : null;

  if (!labelEntry) {
    return count !== null ? `${count} 条` : "待生成统计";
  }

  return count !== null ? `${labelEntry[1]} · ${count}` : String(labelEntry[1]);
}

export function KnowledgeOverview() {
  const [state, setState] = useState<OverviewState>({
    institutions: null,
    scholars: null,
    projects: null,
    events: null,
    leadership: null,
    reports: null,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      const [
        institutions,
        scholars,
        projects,
        events,
        leadership,
        reports,
      ] = await Promise.allSettled([
        fetchInstitutionStats(),
        fetchScholarStats(),
        fetchProjectStats(),
        fetchEventStats(),
        fetchLeadershipAll(),
        fetchReportDimensions(),
      ]);

      if (cancelled) {
        return;
      }

      setState({
        institutions:
          institutions.status === "fulfilled" ? institutions.value : null,
        scholars: scholars.status === "fulfilled" ? scholars.value : null,
        projects: projects.status === "fulfilled" ? projects.value : null,
        events: events.status === "fulfilled" ? events.value : null,
        leadership: leadership.status === "fulfilled" ? leadership.value : null,
        reports: reports.status === "fulfilled" ? reports.value : null,
      });
      setLoading(false);
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const cards = [
    {
      title: "机构网络",
      value: state.institutions?.total_universities ?? 0,
      detail: state.institutions
        ? `${state.institutions.total_departments} 个二级机构`
        : "未连接",
      subdetail: toCountLabel(state.institutions?.by_category),
      icon: Building2,
      tone: "from-blue-500/15 to-cyan-500/10 text-blue-600 dark:text-blue-300",
    },
    {
      title: "学者库",
      value: state.scholars?.total ?? 0,
      detail: state.scholars
        ? `${state.scholars.academicians} 位院士`
        : "未连接",
      subdetail: toCountLabel(state.scholars?.by_university),
      icon: GraduationCap,
      tone: "from-violet-500/15 to-fuchsia-500/10 text-violet-600 dark:text-violet-300",
    },
    {
      title: "项目标签",
      value: state.projects?.total ?? 0,
      detail: state.projects
        ? `${state.projects.total_related_scholars} 条学者关联`
        : "未连接",
      subdetail: toCountLabel(state.projects?.by_category),
      icon: FolderKanban,
      tone: "from-emerald-500/15 to-teal-500/10 text-emerald-600 dark:text-emerald-300",
    },
    {
      title: "活动库",
      value: state.events?.total ?? 0,
      detail: state.events
        ? `${state.events.total_related_scholars} 条活动关联`
        : "未连接",
      subdetail: toCountLabel(state.events?.by_series),
      icon: CalendarRange,
      tone: "from-amber-500/15 to-orange-500/10 text-amber-600 dark:text-amber-300",
    },
    {
      title: "高校领导",
      value: state.leadership?.total ?? 0,
      detail: state.leadership
        ? `${state.leadership.items.reduce((sum, item) => sum + item.leader_count, 0)} 位领导在库`
        : "未连接",
      subdetail:
        state.leadership?.items[0]?.university_name
          ? `最近样本：${state.leadership.items[0].university_name}`
          : "等待抓取结果",
      icon: Landmark,
      tone: "from-rose-500/15 to-pink-500/10 text-rose-600 dark:text-rose-300",
    },
    {
      title: "报告维度",
      value: state.reports?.dimensions.length ?? 0,
      detail: state.reports
        ? `${state.reports.dimensions.filter((item) => item.status === "implemented").length} 个已实现`
        : "未连接",
      subdetail:
        state.reports?.dimensions[0]?.name ?? "等待报告能力加载",
      icon: Sparkles,
      tone: "from-slate-500/15 to-zinc-500/10 text-slate-600 dark:text-slate-300",
    },
  ];

  return (
    <section className="rounded-xl border bg-card overflow-hidden">
      <div className="flex items-center justify-between gap-3 border-b bg-muted/20 px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold">知识能力总览</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Nexus 已同步后的知识库、组织结构与智能报告能力
          </p>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {loading ? "同步中…" : "已对齐后端统计"}
        </span>
      </div>

      <div className="grid gap-4 p-5 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.title}
              className="rounded-xl border bg-background/70 p-4 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {card.title}
                  </p>
                  <div className="mt-3 text-3xl font-black tracking-tight">
                    {card.value.toLocaleString()}
                  </div>
                </div>
                <div
                  className={cn(
                    "flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br",
                    card.tone,
                  )}
                >
                  <Icon className="h-5 w-5" />
                </div>
              </div>

              <div className="mt-4 space-y-1">
                <p className="text-sm font-medium text-foreground/85">
                  {card.detail}
                </p>
                <p className="text-xs text-muted-foreground">{card.subdetail}</p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
