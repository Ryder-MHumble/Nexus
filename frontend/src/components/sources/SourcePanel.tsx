"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CheckSquare,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Search,
  Square,
  X,
} from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fetchSourceCatalog } from "@/lib/api";
import { getDimensionLabel, useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import type {
  DimensionGroup,
  Source,
  SourceFacetItem,
  SourceHealthStatus,
} from "@/types";

const HEALTH_LABEL_MAP: Record<SourceHealthStatus, string> = {
  healthy: "健康",
  warning: "预警",
  failing: "故障",
  unknown: "未知",
};

const HEALTH_BADGE_MAP: Record<SourceHealthStatus, string> = {
  healthy:
    "border-emerald-300 bg-emerald-500/10 text-emerald-700 dark:border-emerald-800 dark:text-emerald-300",
  warning:
    "border-amber-300 bg-amber-500/10 text-amber-700 dark:border-amber-800 dark:text-amber-300",
  failing:
    "border-red-300 bg-red-500/10 text-red-700 dark:border-red-800 dark:text-red-300",
  unknown:
    "border-border/70 bg-muted/60 text-muted-foreground dark:border-border/60",
};

function quickFacetLabel(item: SourceFacetItem) {
  return item.label?.trim() || item.key;
}

function filterSource(
  source: Source,
  search: string,
  methodFilter: string | null,
  healthFilter: SourceHealthStatus | null,
  groupFilter: string | null,
) {
  const q = search.trim().toLowerCase();
  const tagText = (source.tags ?? []).join(" ").toLowerCase();
  const groupText = (source.group ?? "").toLowerCase();

  if (q) {
    const haystack = [
      source.id,
      source.name,
      source.url ?? "",
      source.dimension,
      source.dimension_name ?? "",
      groupText,
      tagText,
    ]
      .join(" ")
      .toLowerCase();
    if (!haystack.includes(q)) {
      return false;
    }
  }

  if (methodFilter && source.crawl_method !== methodFilter) {
    return false;
  }

  if (healthFilter && (source.health_status ?? "unknown") !== healthFilter) {
    return false;
  }

  if (groupFilter && source.group !== groupFilter) {
    return false;
  }

  return true;
}

export function SourcePanel() {
  const {
    sources,
    sourceFacets,
    sourceCatalogTotal,
    selectedIds,
    expandedDimensions,
    setSourceCatalog,
    toggleSource,
    toggleDimension,
    expandDimension,
    status,
  } = useCrawlerStore();

  const [search, setSearch] = useState("");
  const [methodFilter, setMethodFilter] = useState<string | null>(null);
  const [healthFilter, setHealthFilter] = useState<SourceHealthStatus | null>(
    null,
  );
  const [groupFilter, setGroupFilter] = useState<string | null>(null);

  const loadSources = async () => {
    try {
      const data = await fetchSourceCatalog();
      setSourceCatalog(data);
    } catch {
      /* silently fail */
    }
  };

  useEffect(() => {
    void (async () => {
      try {
        const data = await fetchSourceCatalog();
        setSourceCatalog(data);
      } catch {
        /* silently fail */
      }
    })();
  }, [setSourceCatalog]);

  const visibleSources = useMemo(
    () =>
      sources.filter((source) =>
        filterSource(
          source,
          search,
          methodFilter,
          healthFilter,
          groupFilter,
        ),
      ),
    [sources, search, methodFilter, healthFilter, groupFilter],
  );

  const dimensions = useMemo<DimensionGroup[]>(() => {
    const map = new Map<string, DimensionGroup>();
    for (const source of visibleSources) {
      const dimension = source.dimension ?? "other";
      if (!map.has(dimension)) {
        map.set(dimension, {
          name: dimension,
          label: source.dimension_name || getDimensionLabel(dimension),
          sources: [],
        });
      }
      map.get(dimension)!.sources.push(source);
    }
    return [...map.values()];
  }, [visibleSources]);

  const totalSelected = selectedIds.size;
  const totalEnabled = sources.filter((source) => source.is_enabled).length;
  const filteredEnabled = visibleSources.filter((source) => source.is_enabled);
  const allSelected =
    filteredEnabled.length > 0 &&
    filteredEnabled.every((source) => selectedIds.has(source.id));

  const methodOptions = sourceFacets?.crawl_methods.slice(0, 5) ?? [];
  const healthOptions =
    sourceFacets?.health_statuses
      .map((item) => item.key as SourceHealthStatus)
      .filter((item): item is SourceHealthStatus =>
        ["healthy", "warning", "failing", "unknown"].includes(item),
      ) ?? [];
  const groupOptions = sourceFacets?.groups.slice(0, 6) ?? [];

  const handleSelectAll = () => {
    const store = useCrawlerStore.getState();
    const next = new Set(store.selectedIds);
    if (allSelected) {
      filteredEnabled.forEach((source) => next.delete(source.id));
    } else {
      filteredEnabled.forEach((source) => next.add(source.id));
    }
    useCrawlerStore.setState({ selectedIds: next });
  };

  const hasQuickFilters = Boolean(methodFilter || healthFilter || groupFilter);

  return (
    <aside className="flex h-full flex-col border-r bg-muted/10">
      <div className="space-y-3 border-b bg-background/70 px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold">信源目录</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              已选{" "}
              <span
                className={cn(
                  "font-bold",
                  totalSelected > 0 ? "text-primary" : "text-muted-foreground",
                )}
              >
                {totalSelected}
              </span>{" "}
              / 启用 {totalEnabled} 个
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-[11px] font-medium gap-1"
              onClick={handleSelectAll}
              title={allSelected ? "取消筛选结果全选" : "全选筛选结果"}
            >
              {allSelected ? (
                <>
                  <CheckSquare className="h-3 w-3" />
                  取消
                </>
              ) : (
                <>
                  <Square className="h-3 w-3" />
                  全选
                </>
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={loadSources}
              title="刷新信源目录"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <div className="rounded-lg border bg-muted/20 px-3 py-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-medium text-foreground/80">目录概览</span>
            <span className="text-muted-foreground">
              {visibleSources.length}/{sourceCatalogTotal || sources.length}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-[10px]">
            <div className="rounded-md bg-background px-2 py-1.5">
              <div className="text-muted-foreground">维度</div>
              <div className="text-sm font-bold">{dimensions.length}</div>
            </div>
            <div className="rounded-md bg-background px-2 py-1.5">
              <div className="text-muted-foreground">分组</div>
              <div className="text-sm font-bold">
                {sourceFacets?.groups.length ?? 0}
              </div>
            </div>
            <div className="rounded-md bg-background px-2 py-1.5">
              <div className="text-muted-foreground">标签</div>
              <div className="text-sm font-bold">
                {sourceFacets?.tags.length ?? 0}
              </div>
            </div>
          </div>
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索信源、标签或分组…"
            className="w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-7 text-xs ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>

        {methodOptions.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              抓取方式
            </div>
            <div className="flex flex-wrap gap-1.5">
              {methodOptions.map((item) => {
                const active = methodFilter === item.key;
                return (
                  <button
                    key={item.key}
                    onClick={() => setMethodFilter(active ? null : item.key)}
                    className={cn(
                      "rounded-full border px-2 py-1 text-[10px] font-medium transition-colors",
                      active
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-border/70 bg-background text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {quickFacetLabel(item)} · {item.count}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {healthOptions.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              健康状态
            </div>
            <div className="flex flex-wrap gap-1.5">
              {healthOptions.map((item) => {
                const active = healthFilter === item;
                return (
                  <button
                    key={item}
                    onClick={() => setHealthFilter(active ? null : item)}
                    className={cn(
                      "rounded-full border px-2 py-1 text-[10px] font-medium transition-colors",
                      active
                        ? HEALTH_BADGE_MAP[item]
                        : "border-border/70 bg-background text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {HEALTH_LABEL_MAP[item]}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {groupOptions.length > 0 && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                热门分组
              </div>
              {hasQuickFilters && (
                <button
                  onClick={() => {
                    setMethodFilter(null);
                    setHealthFilter(null);
                    setGroupFilter(null);
                  }}
                  className="text-[10px] text-muted-foreground transition-colors hover:text-foreground"
                >
                  清空筛选
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {groupOptions.map((item) => {
                const active = groupFilter === item.key;
                return (
                  <button
                    key={item.key}
                    onClick={() => setGroupFilter(active ? null : item.key)}
                    className={cn(
                      "rounded-full border px-2 py-1 text-[10px] font-medium transition-colors",
                      active
                        ? "border-blue-400/50 bg-blue-500/10 text-blue-600 dark:text-blue-300"
                        : "border-border/70 bg-background text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {quickFacetLabel(item)} · {item.count}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="scrollbar-hide flex-1 overflow-y-auto py-2">
        {dimensions.length === 0 && (
          <p className="py-8 text-center text-xs text-muted-foreground">
            未找到匹配的信源
          </p>
        )}

        {dimensions.map((dimension) => {
          const isExpanded = search.trim()
            ? true
            : expandedDimensions.has(dimension.name);
          const enabledSources = dimension.sources.filter((source) => source.is_enabled);
          const allDimensionSelected =
            enabledSources.length > 0 &&
            enabledSources.every((source) => selectedIds.has(source.id));
          const someSelected = enabledSources.some((source) =>
            selectedIds.has(source.id),
          );
          const selectedCount = enabledSources.filter((source) =>
            selectedIds.has(source.id),
          ).length;

          return (
            <div key={dimension.name} className="mb-0.5">
              <div
                className="mx-1 flex cursor-pointer items-center gap-2 rounded-md px-3 py-2 transition-colors hover:bg-muted/60"
                onClick={() => expandDimension(dimension.name)}
              >
                <Checkbox
                  checked={allDimensionSelected}
                  data-state={
                    someSelected && !allDimensionSelected
                      ? "indeterminate"
                      : undefined
                  }
                  onCheckedChange={() => toggleDimension(dimension.name)}
                  onClick={(event) => event.stopPropagation()}
                  className="h-3.5 w-3.5 shrink-0"
                />
                <span className="flex-1 text-xs font-semibold text-foreground/80">
                  {dimension.label}
                </span>
                {selectedCount > 0 && (
                  <Badge className="h-4 bg-primary/80 px-1.5 text-[10px]">
                    {selectedCount}
                  </Badge>
                )}
                <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                  {dimension.sources.length}
                </Badge>
                <span className="text-muted-foreground">
                  {isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                </span>
              </div>

              {isExpanded && (
                <div className="space-y-1 pb-1 pl-4 pr-2">
                  {dimension.sources.map((source) => {
                    const isSelected = selectedIds.has(source.id);
                    const isCurrent = status.current_source === source.id;
                    const isCompleted = status.completed_sources.includes(source.id);
                    const isFailed = status.failed_sources.includes(source.id);
                    const healthStatus = source.health_status ?? "unknown";

                    return (
                      <label
                        key={source.id}
                        className={cn(
                          "flex cursor-pointer gap-2 rounded-lg px-2 py-2 transition-colors hover:bg-muted/60",
                          !source.is_enabled && "cursor-not-allowed opacity-40",
                          isCurrent && "bg-blue-500/10 ring-1 ring-blue-500/30",
                          isCompleted && !isCurrent && "bg-emerald-500/5",
                          isFailed && "bg-destructive/5",
                        )}
                      >
                        <Checkbox
                          checked={isSelected}
                          disabled={!source.is_enabled}
                          onCheckedChange={() => toggleSource(source.id)}
                          className="mt-0.5 h-3.5 w-3.5 shrink-0"
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-2">
                            <span
                              className={cn(
                                "truncate text-xs font-medium",
                                isSelected ? "text-foreground" : "text-foreground/85",
                              )}
                            >
                              {source.name}
                            </span>
                            <Badge
                              variant="outline"
                              className={cn(
                                "h-5 shrink-0 px-1.5 text-[10px]",
                                HEALTH_BADGE_MAP[healthStatus],
                              )}
                            >
                              {HEALTH_LABEL_MAP[healthStatus]}
                            </Badge>
                          </div>

                          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-muted-foreground">
                            {source.crawl_method && (
                              <Badge variant="secondary" className="h-4 px-1.5">
                                {source.crawl_method}
                              </Badge>
                            )}
                            {source.group && (
                              <Badge variant="outline" className="h-4 px-1.5">
                                {source.group}
                              </Badge>
                            )}
                            {source.is_enabled_overridden && (
                              <Badge className="h-4 bg-blue-500/15 px-1.5 text-[10px] text-blue-600 dark:text-blue-300">
                                runtime
                              </Badge>
                            )}
                            {typeof source.consecutive_failures === "number" &&
                              source.consecutive_failures > 0 && (
                                <span>失败 {source.consecutive_failures} 次</span>
                              )}
                          </div>

                          {(source.tags?.length ?? 0) > 0 && (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {source.tags!.slice(0, 3).map((tag) => (
                                <span
                                  key={`${source.id}-${tag}`}
                                  className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                                >
                                  #{tag}
                                </span>
                              ))}
                              {source.tags!.length > 3 && (
                                <span className="text-[10px] text-muted-foreground">
                                  +{source.tags!.length - 3}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
