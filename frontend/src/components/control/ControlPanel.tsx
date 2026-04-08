'use client'

import { AlertCircle, HardDrive, Loader2, Play, SlidersHorizontal, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCrawlerStore } from '@/lib/store'
import { cn } from '@/lib/utils'

const EXPORT_LABEL_MAP = {
  json: 'JSON',
  csv: 'CSV',
  database: '数据库',
} as const

export function ControlPanel() {
  const {
    selectedIds,
    whitelistInput,
    blacklistInput,
    exportFormat,
    status,
    isStarting,
    isStopping,
    error,
    startCrawl,
    stopCrawl,
  } = useCrawlerStore()

  const canStart = selectedIds.size > 0 && !status.is_running && !isStarting
  const canStop = status.is_running && !isStopping
  const whitelistCount = whitelistInput
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean).length
  const blacklistCount = blacklistInput
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean).length

  return (
    <section className="overflow-hidden rounded-2xl border bg-card/90 shadow-sm backdrop-blur-sm">
      <div className="p-6">
        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Crawl Control
            </p>
            <h2 className="mt-2 text-xl font-bold tracking-tight">爬取控制</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {selectedIds.size > 0 ? (
                <>
                  已选择 <span className="font-bold text-primary">{selectedIds.size}</span> 个信源，
                  可以直接启动本轮任务
                </>
              ) : (
                '先在左侧目录勾选信源，再决定过滤与导出方式'
              )}
            </p>
          </div>

          <div
            aria-live="polite"
            className={cn(
              'inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold',
              status.is_running
                ? 'border-blue-500/40 bg-blue-500/10 text-blue-600 dark:text-blue-300'
                : 'border-border bg-muted/40 text-muted-foreground'
            )}
          >
            <span
              className={cn(
                'h-2.5 w-2.5 rounded-full',
                status.is_running ? 'bg-blue-500 animate-pulse' : 'bg-muted-foreground/40'
              )}
            />
            {status.is_running ? '运行中' : '就绪'}
          </div>
        </div>

        <div className="mb-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border bg-background/80 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              已选信源
            </p>
            <div className="mt-2 text-3xl font-black tracking-tight">
              {selectedIds.size}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              未选择时不会发起爬取
            </p>
          </div>

          <div className="rounded-xl border bg-background/80 p-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              <HardDrive className="h-3.5 w-3.5" />
              导出方式
            </div>
            <div className="mt-2 text-xl font-bold">
              {EXPORT_LABEL_MAP[exportFormat]}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {exportFormat === 'database' ? '结果直接入库' : '任务完成后可下载'}
            </p>
          </div>

          <div className="rounded-xl border bg-background/80 p-4">
            <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              <SlidersHorizontal className="h-3.5 w-3.5" />
              关键词过滤
            </div>
            <div className="mt-2 flex items-end gap-3">
              <div>
                <div className="text-xl font-bold text-emerald-600 dark:text-emerald-400">
                  {whitelistCount}
                </div>
                <p className="text-[11px] text-muted-foreground">白名单</p>
              </div>
              <div>
                <div className="text-xl font-bold text-red-500 dark:text-red-400">
                  {blacklistCount}
                </div>
                <p className="text-[11px] text-muted-foreground">黑名单</p>
              </div>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              黑名单优先于白名单
            </p>
          </div>
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/10 px-3 py-2.5">
            <AlertCircle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
            <p className="text-xs text-destructive leading-snug">{error}</p>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Button
            size="lg"
            className={cn(
              "h-12 gap-2 text-sm font-bold shadow-md transition-all",
              status.is_running && "ring-2 ring-blue-500/50 ring-offset-2 ring-offset-background"
            )}
            disabled={!canStart}
            onClick={startCrawl}
          >
            {isStarting ? (
              <><Loader2 className="h-4 w-4 animate-spin" />启动中…</>
            ) : (
              <><Play className="h-4 w-4 fill-current" />开始爬取</>
            )}
          </Button>

          <Button
            size="lg"
            variant="destructive"
            className="h-12 text-sm font-bold gap-2 shadow-md"
            disabled={!canStop}
            onClick={stopCrawl}
          >
            {isStopping ? (
              <><Loader2 className="h-4 w-4 animate-spin" />停止中…</>
            ) : (
              <><Square className="h-4 w-4 fill-current" />停止爬取</>
            )}
          </Button>
        </div>
      </div>
    </section>
  )
}
