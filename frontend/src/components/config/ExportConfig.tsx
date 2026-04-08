"use client";

import { Database, FileJson, FileSpreadsheet, HardDrive } from "lucide-react";
import { useCrawlerStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import type { ExportFormat } from "@/types";

const OPTIONS: {
  value: ExportFormat;
  label: string;
  desc: string;
  icon: React.ReactNode;
  color: string;
  selectedBg: string;
}[] = [
  {
    value: "json",
    label: "JSON",
    desc: "结构化数据",
    icon: <FileJson className="h-4 w-4" />,
    color: "text-amber-500",
    selectedBg: "border-amber-400/60 bg-amber-500/10 dark:border-amber-500/40",
  },
  {
    value: "csv",
    label: "CSV",
    desc: "表格数据",
    icon: <FileSpreadsheet className="h-4 w-4" />,
    color: "text-emerald-500",
    selectedBg:
      "border-emerald-400/60 bg-emerald-500/10 dark:border-emerald-500/40",
  },
  {
    value: "database",
    label: "数据库",
    desc: "直接存储",
    icon: <Database className="h-4 w-4" />,
    color: "text-blue-500",
    selectedBg: "border-blue-400/60 bg-blue-500/10 dark:border-blue-500/40",
  },
];

export function ExportConfig() {
  const { exportFormat, setExportFormat, status } = useCrawlerStore();
  const disabled = status.is_running;

  return (
    <section className="overflow-hidden rounded-2xl border bg-card/90 shadow-sm backdrop-blur-sm">
      <div className="flex items-center gap-2 px-4 py-3 border-b bg-muted/10">
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
          <HardDrive className="h-3 w-3 text-primary" />
        </div>
        <div>
          <h2 className="text-sm font-semibold">导出格式</h2>
          <p className="text-[10px] text-muted-foreground">
            {disabled ? "任务运行中不可切换" : "开始前确认结果落地方式"}
          </p>
        </div>
      </div>

      <div className="p-4">
        <div className="flex flex-col gap-2">
          {OPTIONS.map((opt) => {
            const isSelected = exportFormat === opt.value;
            return (
              <button
                type="button"
                key={opt.value}
                disabled={disabled}
                onClick={() => setExportFormat(opt.value)}
                aria-pressed={isSelected}
                className={cn(
                  "relative flex items-center gap-3 rounded-lg border-2 p-3 text-left transition-all",
                  "hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  isSelected
                    ? opt.selectedBg
                    : "border-border/60 bg-background hover:bg-muted/30",
                )}
              >
                {isSelected && (
                  <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-primary" />
                )}
                <span
                  className={cn(
                    opt.color,
                    "transition-transform shrink-0",
                    isSelected && "scale-110",
                  )}
                >
                  {opt.icon}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-bold">{opt.label}</div>
                  <div className="text-[10px] text-muted-foreground">
                    {opt.desc}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
