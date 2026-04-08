"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
    expandDimension,
    status,
  } = useCrawlerStore();

  const [search, setSearch] = useState("");
  const [methodFilter, setMethodFilter] = useState<string | null>(null);
  const [healthFilter, setHealthFilter] = useState<SourceHealthStatus | null>(
    null,
  );
  const [groupFilter, setGroupFilter] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [hasLoadedOnce, setHasLoadedOnce] = useState(false);

  const loadSources = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await fetchSourceCatalog();
      setSourceCatalog(data);
      setHasLoadedOnce(true);
    } catch (error) {
      setLoadError(
        error instanceof Error ? error.message : "信源目录加载失败，请稍后重试",
      );
    } finally {
      setIsLoading(false);
    }
  }, [setSourceCatalog]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

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

  const handleToggleVisibleDimension = (dimensionSources: Source[]) => {
    const enabledSources = dimensionSources.filter((source) => source.is_enabled);
    if (enabledSources.length === 0) {
      return;
    }

    const next = new Set(useCrawlerStore.getState().selectedIds);
    const everySelected = enabledSources.every((source) => next.has(source.id));

    if (everySelected) {
      enabledSources.forEach((source) => next.delete(source.id));
    } else {
      enabledSources.forEach((source) => next.add(source.id));
    }

    useCrawlerStore.setState({ selectedIds: next });
  };

  const hasQuickFilters = Boolean(methodFilter || healthFilter || groupFilter);
  const showNoResults =
    !isLoading && !loadError && hasLoadedOnce && dimensions.length === 0;
  const showLoadFailure = !isLoading && sources.length === 0 && Boolean(loadError);
  const showStaleWarning = Boolean(loadError) && sources.length > 0;

  return (
    <aside className="flex h-full min-h-[640px] flex-col overflow-hidden rounded-2xl border bg-card/90 shadow-sm backdrop-blur-sm xl:max-h-[calc(100vh-6rem)]">
      <div className="space-y-3 border-b bg-background/80 px-4 py-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Source Directory
            </p>
            <h2 className="mt-2 text-lg font-semibold tracking-tight">信源目录</h2>
            <p className="mt-1 text-xs text-muted-foreground">
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
              disabled={filteredEnabled.length === 0}
              aria-label={allSelected ? "取消筛选结果全选" : "全选筛选结果"}
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
              disabled={isLoading}
              title="刷新信源目录"
              aria-label="刷新信源目录"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
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
            aria-label="搜索信源、标签或分组"
            className="w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-7 text-xs ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch("")}
              aria-label="清空搜索关键词"
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
                    type="button"
                    key={item.key}
                    onClick={() => setMethodFilter(active ? null : item.key)}
                    aria-pressed={active}
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
                    type="button"
                    key={item}
                    onClick={() => setHealthFilter(active ? null : item)}
                    aria-pressed={active}
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
                  type="button"
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
                    type="button"
                    key={item.key}
                    onClick={() => setGroupFilter(active ? null : item.key)}
                    aria-pressed={active}
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

      <div className="flex-1 overflow-y-auto py-3 scrollbar-thin">
        {showStaleWarning && (
          <div className="mx-3 mb-3 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2.5">
            <p className="text-xs font-semibold text-amber-700 dark:text-amber-200">
              信源目录同步失败
            </p>
            <p className="mt-1 text-[11px] text-amber-700/90 dark:text-amber-100/90">
              {loadError} 当前展示的是最近一次成功同步的目录数据。
            </p>
          </div>
        )}

        {isLoading && sources.length === 0 && (
          <div className="mx-3 rounded-xl border border-dashed bg-background/70 px-4 py-6">
            <p className="text-sm font-medium">正在加载信源目录…</p>
            <p className="mt-1 text-xs text-muted-foreground">
              首次同步可能需要几秒钟。
            </p>
          </div>
        )}

        {showLoadFailure && (
          <div className="mx-3 rounded-xl border border-dashed bg-background/70 px-4 py-6">
            <p className="text-sm font-medium">信源目录暂时不可用</p>
            <p className="mt-1 text-xs text-muted-foreground">{loadError}</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => {
                void loadSources();
              }}
            >
              重试加载
            </Button>
          </div>
        )}

        {showNoResults && (
          <div className="mx-3 rounded-xl border border-dashed bg-background/70 px-4 py-6">
            <p className="text-sm font-medium">未找到匹配的信源</p>
            <p className="mt-1 text-xs text-muted-foreground">
              可以调整搜索词或清空上方的快速筛选。
            </p>
          </div>
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
            <div key={dimension.name} className="mb-1 px-2">
              <div className="flex items-center gap-2 rounded-xl border bg-background/60 px-2.5 py-2">
                <Checkbox
                  checked={allDimensionSelected}
                  data-state={
                    someSelected && !allDimensionSelected
                      ? "indeterminate"
                      : undefined
                  }
                  onCheckedChange={() => handleToggleVisibleDimension(dimension.sources)}
                  aria-label={`切换 ${dimension.label} 维度的全部信源`}
                  className="h-3.5 w-3.5 shrink-0"
                />
                <button
                  type="button"
                  onClick={() => expandDimension(dimension.name)}
                  aria-expanded={isExpanded}
                  aria-controls={`dimension-panel-${dimension.name}`}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <span className="flex-1 truncate text-xs font-semibold text-foreground/80">
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
                </button>
              </div>

              {isExpanded && (
                <div
                  id={`dimension-panel-${dimension.name}`}
                  className="space-y-1 pb-1 pl-3 pr-1 pt-1.5"
                >
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
                          aria-label={`选择信源 ${source.name}`}
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
                            {(isCurrent || isCompleted || isFailed) && (
                              <Badge
                                className={cn(
                                  "h-4 px-1.5 text-[10px]",
                                  isCurrent &&
                                    "bg-blue-500/15 text-blue-600 dark:text-blue-300",
                                  isCompleted &&
                                    !isCurrent &&
                                    "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
                                  isFailed &&
                                    "bg-destructive/15 text-destructive",
                                )}
                              >
                                {isCurrent
                                  ? "进行中"
                                  : isCompleted
                                    ? "完成"
                                    : "失败"}
                              </Badge>
                            )}
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

                          {(source.tags?.length ?? 0) > 0 &&
                            (isSelected || isCurrent || search.trim().length > 0) && (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {source.tags!.slice(0, 2).map((tag) => (
                                <span
                                  key={`${source.id}-${tag}`}
                                  className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                                >
                                  #{tag}
                                </span>
                              ))}
                              {source.tags!.length > 2 && (
                                <span className="text-[10px] text-muted-foreground">
                                  +{source.tags!.length - 2}
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
