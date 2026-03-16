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
import { Separator } from "@/components/ui/separator";
import { fetchSources } from "@/lib/api";
import { getDimensionLabel, useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import type { DimensionGroup } from "@/types";

export function SourcePanel() {
  const {
    sources,
    selectedIds,
    expandedDimensions,
    setSources,
    toggleSource,
    toggleDimension,
    expandDimension,
    status,
  } = useCrawlerStore();

  const [search, setSearch] = useState("");

  const loadSources = async () => {
    try {
      const data = await fetchSources();
      setSources(data);
    } catch {
      /* silently fail */
    }
  };

  useEffect(() => {
    loadSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const dimensions = useMemo<DimensionGroup[]>(() => {
    const map = new Map<string, DimensionGroup>();
    for (const s of sources) {
      const dim = s.dimension ?? "other";
      if (!map.has(dim)) {
        map.set(dim, { name: dim, label: getDimensionLabel(dim), sources: [] });
      }
      map.get(dim)!.sources.push(s);
    }
    return [...map.values()];
  }, [sources]);

  const filteredDimensions = useMemo<DimensionGroup[]>(() => {
    if (!search.trim()) return dimensions;
    const q = search.trim().toLowerCase();
    return dimensions
      .map((dim) => ({
        ...dim,
        sources: dim.sources.filter((s) => s.name.toLowerCase().includes(q)),
      }))
      .filter((dim) => dim.sources.length > 0);
  }, [dimensions, search]);

  const totalSelected = selectedIds.size;
  const totalEnabled = sources.filter((s) => s.is_enabled).length;

  const allEnabled = sources.filter((s) => s.is_enabled);
  const allSelected =
    allEnabled.length > 0 && allEnabled.every((s) => selectedIds.has(s.id));

  const handleSelectAll = () => {
    const store = useCrawlerStore.getState();
    if (allSelected) {
      // Clear all
      const next = new Set(store.selectedIds);
      allEnabled.forEach((s) => next.delete(s.id));
      useCrawlerStore.setState({ selectedIds: next });
    } else {
      // Select all enabled
      const next = new Set(store.selectedIds);
      allEnabled.forEach((s) => next.add(s.id));
      useCrawlerStore.setState({ selectedIds: next });
    }
  };

  return (
    <aside className="flex flex-col border-r h-full bg-muted/10">
      {/* Panel header */}
      <div className="px-4 py-3 space-y-3 border-b bg-background/50">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold">信源选择</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              已选{" "}
              <span
                className={cn(
                  "font-bold",
                  totalSelected > 0 ? "text-primary" : "text-muted-foreground",
                )}
              >
                {totalSelected}
              </span>{" "}
              / 共 {totalEnabled} 个
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-[11px] font-medium gap-1"
              onClick={handleSelectAll}
              title={allSelected ? "取消全选" : "全选"}
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
              title="刷新信源列表"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* Search box */}
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索信源…"
            className="w-full rounded-md border border-input bg-background pl-8 pr-7 py-1.5 text-xs ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* Dimension groups */}
      <div className="flex-1 overflow-y-auto scrollbar-hide py-2">
        {filteredDimensions.length === 0 && (
          <p className="text-center text-xs text-muted-foreground py-8">
            未找到匹配的信源
          </p>
        )}

        {filteredDimensions.map((dim) => {
          const isExpanded = search.trim()
            ? true
            : expandedDimensions.has(dim.name);
          const enabledSources = dim.sources.filter((s) => s.is_enabled);
          const allSelected =
            enabledSources.length > 0 &&
            enabledSources.every((s) => selectedIds.has(s.id));
          const someSelected = enabledSources.some((s) =>
            selectedIds.has(s.id),
          );
          const selectedCount = enabledSources.filter((s) =>
            selectedIds.has(s.id),
          ).length;

          return (
            <div key={dim.name} className="mb-0.5">
              {/* Dimension header row */}
              <div
                className="flex items-center gap-2 px-3 py-2 rounded-md mx-1 cursor-pointer hover:bg-muted/60 transition-colors"
                onClick={() => expandDimension(dim.name)}
              >
                <Checkbox
                  checked={allSelected}
                  data-state={
                    someSelected && !allSelected ? "indeterminate" : undefined
                  }
                  onCheckedChange={() => toggleDimension(dim.name)}
                  onClick={(e) => e.stopPropagation()}
                  className="h-3.5 w-3.5 shrink-0"
                />
                <span className="flex-1 text-xs font-semibold text-foreground/80">
                  {dim.label}
                </span>
                {selectedCount > 0 && (
                  <Badge
                    variant="default"
                    className="text-[10px] h-4 px-1.5 bg-primary/80"
                  >
                    {selectedCount}
                  </Badge>
                )}
                <Badge variant="secondary" className="text-[10px] h-4 px-1.5">
                  {dim.sources.length}
                </Badge>
                <span className="text-muted-foreground">
                  {isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                </span>
              </div>

              {/* Source list */}
              {isExpanded && (
                <div className="pl-4 pr-2 pb-1">
                  {dim.sources.map((source) => {
                    const isSelected = selectedIds.has(source.id);
                    const isCurrent = status.current_source === source.id;
                    const isCompleted = status.completed_sources.includes(
                      source.id,
                    );
                    const isFailed = status.failed_sources.includes(source.id);

                    return (
                      <label
                        key={source.id}
                        className={cn(
                          "flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer",
                          "hover:bg-muted/60 transition-colors",
                          !source.is_enabled && "opacity-40 cursor-not-allowed",
                          isCurrent && "bg-blue-500/10 ring-1 ring-blue-500/30",
                          isCompleted && !isCurrent && "bg-emerald-500/5",
                          isFailed && "bg-destructive/5",
                        )}
                      >
                        <Checkbox
                          checked={isSelected}
                          disabled={!source.is_enabled}
                          onCheckedChange={() => toggleSource(source.id)}
                          className="h-3.5 w-3.5 shrink-0"
                        />
                        <span
                          className={cn(
                            "flex-1 text-xs truncate",
                            isSelected
                              ? "text-foreground font-medium"
                              : "text-muted-foreground",
                          )}
                        >
                          {source.name}
                        </span>

                        {isCurrent && (
                          <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse shrink-0" />
                        )}
                        {isCompleted && !isCurrent && (
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
                        )}
                        {isFailed && (
                          <span className="h-1.5 w-1.5 rounded-full bg-destructive shrink-0" />
                        )}
                        {!source.is_enabled && (
                          <Badge
                            variant="outline"
                            className="text-[9px] h-3.5 px-1 shrink-0 text-muted-foreground"
                          >
                            禁用
                          </Badge>
                        )}
                      </label>
                    );
                  })}
                </div>
              )}
              <Separator className="mx-2 opacity-30" />
            </div>
          );
        })}
      </div>
    </aside>
  );
}
