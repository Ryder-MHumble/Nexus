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

type OverviewAvailability = Record<keyof OverviewState, boolean>;

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
  const [availability, setAvailability] = useState<OverviewAvailability>({
    institutions: false,
    scholars: false,
    projects: false,
    events: false,
    leadership: false,
    reports: false,
  });

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
      setAvailability({
        institutions: institutions.status === "fulfilled",
        scholars: scholars.status === "fulfilled",
        projects: projects.status === "fulfilled",
        events: events.status === "fulfilled",
        leadership: leadership.status === "fulfilled",
        reports: reports.status === "fulfilled",
      });
      setLoading(false);
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const unavailableCount = Object.values(availability).filter((item) => !item).length;

  const cards = [
    {
      title: "机构网络",
      value: state.institutions?.total_universities,
      valueLabel: state.institutions
        ? state.institutions.total_universities.toLocaleString()
        : "—",
      detail: state.institutions
        ? `${state.institutions.total_departments} 个二级机构`
        : availability.institutions
          ? "等待统计生成"
          : "统计接口未连通",
      subdetail: toCountLabel(state.institutions?.by_category),
      available: availability.institutions,
      icon: Building2,
      tone: "from-blue-500/15 to-cyan-500/10 text-blue-600 dark:text-blue-300",
    },
    {
      title: "学者库",
      value: state.scholars?.total,
      valueLabel: state.scholars ? state.scholars.total.toLocaleString() : "—",
      detail: state.scholars
        ? `${state.scholars.academicians} 位院士`
        : availability.scholars
          ? "等待统计生成"
          : "统计接口未连通",
      subdetail: toCountLabel(state.scholars?.by_university),
      available: availability.scholars,
      icon: GraduationCap,
      tone: "from-violet-500/15 to-fuchsia-500/10 text-violet-600 dark:text-violet-300",
    },
    {
      title: "项目标签",
      value: state.projects?.total,
      valueLabel: state.projects ? state.projects.total.toLocaleString() : "—",
      detail: state.projects
        ? `${state.projects.total_related_scholars} 条学者关联`
        : availability.projects
          ? "等待统计生成"
          : "统计接口未连通",
      subdetail: toCountLabel(state.projects?.by_category),
      available: availability.projects,
      icon: FolderKanban,
      tone: "from-emerald-500/15 to-teal-500/10 text-emerald-600 dark:text-emerald-300",
    },
    {
      title: "活动库",
      value: state.events?.total,
      valueLabel: state.events ? state.events.total.toLocaleString() : "—",
      detail: state.events
        ? `${state.events.total_related_scholars} 条活动关联`
        : availability.events
          ? "等待统计生成"
          : "统计接口未连通",
      subdetail: toCountLabel(state.events?.by_series),
      available: availability.events,
      icon: CalendarRange,
      tone: "from-amber-500/15 to-orange-500/10 text-amber-600 dark:text-amber-300",
    },
    {
      title: "高校领导",
      value: state.leadership?.total,
      valueLabel: state.leadership ? state.leadership.total.toLocaleString() : "—",
      detail: state.leadership
        ? `${state.leadership.items.reduce((sum, item) => sum + item.leader_count, 0)} 位领导在库`
        : availability.leadership
          ? "等待抓取结果"
          : "领导接口未连通",
      subdetail:
        state.leadership?.items[0]?.university_name
          ? `最近样本：${state.leadership.items[0].university_name}`
          : "等待抓取结果",
      available: availability.leadership,
      icon: Landmark,
      tone: "from-rose-500/15 to-pink-500/10 text-rose-600 dark:text-rose-300",
    },
    {
      title: "报告维度",
      value: state.reports?.dimensions.length,
      valueLabel: state.reports
        ? state.reports.dimensions.length.toLocaleString()
        : "—",
      detail: state.reports
        ? `${state.reports.dimensions.filter((item) => item.status === "implemented").length} 个已实现`
        : availability.reports
          ? "等待能力加载"
          : "报告接口未连通",
      subdetail:
        state.reports?.dimensions[0]?.name ?? "等待报告能力加载",
      available: availability.reports,
      icon: Sparkles,
      tone: "from-slate-500/15 to-zinc-500/10 text-slate-600 dark:text-slate-300",
    },
  ];

  return (
    <section className="overflow-hidden rounded-2xl border bg-card/90 shadow-sm backdrop-blur-sm">
      <div className="flex items-center justify-between gap-3 border-b bg-muted/20 px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold">知识能力总览</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Nexus 已同步后的知识库、组织结构与智能报告能力
          </p>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {loading
            ? "同步中…"
            : unavailableCount > 0
              ? `${unavailableCount} 项未连通`
              : "已对齐后端统计"}
        </span>
      </div>

      {!loading && unavailableCount > 0 && (
        <div className="border-b border-amber-500/20 bg-amber-500/10 px-5 py-3">
          <p className="text-xs text-amber-700 dark:text-amber-200">
            部分统计接口未返回结果，卡片会明确显示为“未连通”，不会再把失败误显示成 0。
          </p>
        </div>
      )}

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
                    {card.valueLabel}
                  </div>
                </div>
                <div
                  className={cn(
                    "flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br",
                    card.tone,
                    !card.available && "opacity-60 grayscale",
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
