'use client'

import { useState } from 'react'
import { Filter, RotateCcw, X } from 'lucide-react'
import { useCrawlerStore } from '@/lib/store'
import { DOMAIN_COLOR_MAP, DOMAINS, type Subdomain } from '@/lib/domains'
import { cn } from '@/lib/utils'

// ─── Tag chip input ──────────────────────────────────────────────────────────

function TagInput({
  value,
  onChange,
  placeholder,
  disabled,
  variant = 'default',
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  disabled?: boolean
  variant?: 'default' | 'whitelist' | 'blacklist'
}) {
  const tags = value
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)

  const variantStyles = {
    whitelist: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
    blacklist: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30',
    default: 'bg-primary/10 text-primary border-primary/30'
  }

  return (
    <div className="space-y-2">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="w-full rounded-lg border border-input bg-background px-3 py-2 text-xs ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      />
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className={cn(
                'inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-medium',
                variantStyles[variant]
              )}
            >
              {tag}
              {!disabled && (
                <button
                  onClick={() => onChange(tags.filter((t) => t !== tag).join(', '))}
                  className="hover:opacity-60 transition-opacity"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Domain picker ───────────────────────────────────────────────────────────

export function FilterConfig() {
  const { whitelistInput, blacklistInput, setWhitelistInput, setBlacklistInput, status } =
    useCrawlerStore()

  const disabled = status.is_running

  const [activeDomain, setActiveDomain] = useState<string | null>(null)
  const [selectedSubs, setSelectedSubs] = useState<Set<string>>(new Set())

  const currentKeywords = new Set(
    whitelistInput
      .split(',')
      .map((k) => k.trim())
      .filter(Boolean),
  )

  function applySubdomain(sub: Subdomain, domainKey: string) {
    const subId = `${domainKey}.${sub.key}`
    const next = new Set(selectedSubs)

    if (next.has(subId)) {
      next.delete(subId)
      const toRemove = new Set(sub.keywords)
      const remaining = [...currentKeywords].filter((k) => !toRemove.has(k))
      setWhitelistInput(remaining.join(', '))
    } else {
      next.add(subId)
      const merged = [...new Set([...currentKeywords, ...sub.keywords])]
      setWhitelistInput(merged.join(', '))
    }
    setSelectedSubs(next)
  }

  function resetDomainFilter() {
    setSelectedSubs(new Set())
    setActiveDomain(null)
    setWhitelistInput('')
  }

  const hasSelection = selectedSubs.size > 0 || currentKeywords.size > 0

  return (
    <div className="rounded-xl border bg-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b bg-muted/10">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
            <Filter className="h-3 w-3 text-primary" />
          </div>
          <h2 className="text-sm font-semibold">领域过滤</h2>
          <span className="text-[10px] text-muted-foreground">可选</span>
        </div>
        {hasSelection && !disabled && (
          <button
            onClick={resetDomainFilter}
            className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
          >
            <RotateCcw className="h-3 w-3" />
            重置
          </button>
        )}
      </div>

      <div className="p-4 space-y-4">
        {/* Domain tabs - compact */}
        <div className="flex flex-wrap gap-1.5">
          {DOMAINS.map((dom) => {
            const colors = DOMAIN_COLOR_MAP[dom.color]
            const isActive = activeDomain === dom.key
            const hasSelectedSub = dom.subdomains.some((s) =>
              selectedSubs.has(`${dom.key}.${s.key}`),
            )

            return (
              <button
                key={dom.key}
                disabled={disabled}
                onClick={() => setActiveDomain(isActive ? null : dom.key)}
                className={cn(
                  'relative inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-all',
                  'disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none',
                  isActive
                    ? `${colors.activeBg} ${colors.text} ${colors.border}`
                    : `bg-background border-border/60 text-muted-foreground hover:border-border`,
                )}
              >
                {dom.name}
                {hasSelectedSub && (
                  <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', colors.text.split(' ')[0].replace('text-', 'bg-'))} />
                )}
              </button>
            )
          })}
        </div>

        {/* Subdomain chips */}
        {activeDomain && (
          <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
            {(() => {
              const dom = DOMAINS.find((d) => d.key === activeDomain)!
              const colors = DOMAIN_COLOR_MAP[dom.color]
              return (
                <>
                  <p className={cn('text-[10px] font-semibold', colors.text)}>
                    {dom.name} · 子领域
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {dom.subdomains.map((sub) => {
                      const subId = `${dom.key}.${sub.key}`
                      const isSelected = selectedSubs.has(subId)
                      return (
                        <button
                          key={sub.key}
                          disabled={disabled}
                          onClick={() => applySubdomain(sub, dom.key)}
                          className={cn(
                            'inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-medium transition-all',
                            'disabled:opacity-40 disabled:cursor-not-allowed',
                            isSelected
                              ? `${colors.activeBg} ${colors.text} ${colors.border}`
                              : 'bg-background border-border/60 text-muted-foreground hover:bg-muted/50',
                          )}
                        >
                          {isSelected && (
                            <span className="h-1 w-1 rounded-full bg-current shrink-0" />
                          )}
                          {sub.name}
                          <span className="text-[9px] opacity-50">({sub.keywords.length})</span>
                        </button>
                      )
                    })}
                  </div>
                </>
              )
            })()}
          </div>
        )}

        {/* Keyword inputs - side by side */}
        <div className="grid grid-cols-2 gap-3 pt-2 border-t">
          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
              白名单
            </label>
            <TagInput
              value={whitelistInput}
              onChange={(v) => {
                setWhitelistInput(v)
                if (!v.trim()) setSelectedSubs(new Set())
              }}
              placeholder="保留这些词..."
              disabled={disabled}
              variant="whitelist"
            />
          </div>

          <div className="space-y-1.5">
            <label className="flex items-center gap-1.5 text-[10px] font-semibold text-red-500 dark:text-red-400">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" />
              黑名单
            </label>
            <TagInput
              value={blacklistInput}
              onChange={setBlacklistInput}
              placeholder="排除这些词..."
              disabled={disabled}
              variant="blacklist"
            />
          </div>
        </div>

        <p className="text-[10px] text-muted-foreground">
          逗号分隔多个关键词 · 优先级：黑名单 &gt; 白名单
        </p>
      </div>
    </div>
  )
}
