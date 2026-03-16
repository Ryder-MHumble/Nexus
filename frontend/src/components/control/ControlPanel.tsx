'use client'

import { AlertCircle, Loader2, Play, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useCrawlerStore } from '@/lib/store'
import { cn } from '@/lib/utils'

export function ControlPanel() {
  const { selectedIds, status, isStarting, isStopping, error, startCrawl, stopCrawl } =
    useCrawlerStore()

  const canStart = selectedIds.size > 0 && !status.is_running && !isStarting
  const canStop = status.is_running && !isStopping

  return (
    <div className="rounded-xl border-2 bg-gradient-to-br from-card to-muted/20 overflow-hidden shadow-sm">
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-bold">爬取控制</h2>
            <p className="text-xs text-muted-foreground mt-1">
              {selectedIds.size > 0 ? (
                <>
                  已选择 <span className="font-bold text-primary">{selectedIds.size}</span> 个信源
                </>
              ) : (
                '请先在左侧选择信源'
              )}
            </p>
          </div>

          {/* Status indicator */}
          <div className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-full border-2 font-semibold text-sm',
            status.is_running
              ? 'bg-blue-500/10 border-blue-500/50 text-blue-600 dark:text-blue-400'
              : 'bg-muted border-border text-muted-foreground'
          )}>
            <span className={cn(
              'h-2.5 w-2.5 rounded-full',
              status.is_running ? 'bg-blue-500 animate-pulse' : 'bg-muted-foreground/40'
            )} />
            {status.is_running ? '运行中' : '就绪'}
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2.5 mb-4">
            <AlertCircle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
            <p className="text-xs text-destructive leading-snug">{error}</p>
          </div>
        )}

        {/* Action buttons - side by side */}
        <div className="grid grid-cols-2 gap-3">
          <Button
            size="lg"
            className={cn(
              "h-12 text-sm font-bold gap-2 transition-all shadow-md",
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
    </div>
  )
}
