import { Header } from "@/components/layout/Header";
import { KnowledgeOverview } from "@/components/dashboard/KnowledgeOverview";
import { IntelligencePanel } from "@/components/dashboard/IntelligencePanel";
import { SourcePanel } from "@/components/sources/SourcePanel";
import { FilterConfig } from "@/components/config/FilterConfig";
import { ExportConfig } from "@/components/config/ExportConfig";
import { ControlPanel } from "@/components/control/ControlPanel";
import { StatusPanel } from "@/components/control/StatusPanel";
import { ResultList } from "@/components/results/ResultList";

export default function Home() {
  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="mx-auto grid max-w-[1680px] gap-6 px-4 pb-8 pt-4 sm:px-6 xl:grid-cols-[340px_minmax(0,1fr)] 2xl:grid-cols-[360px_minmax(0,1fr)]">
        <div className="xl:sticky xl:top-20 xl:self-start">
          <SourcePanel />
        </div>

        <div className="min-w-0 space-y-8">
          <section className="space-y-3">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                执行区
              </p>
              <h2 className="text-xl font-semibold tracking-tight">
                先选信源，再启动任务
              </h2>
              <p className="max-w-3xl text-sm text-muted-foreground">
                执行相关的控制、过滤和导出配置集中在这里，避免运行中再来回切换信息区。
              </p>
            </div>
            <div className="grid gap-6 2xl:grid-cols-[minmax(0,1.25fr)_360px]">
              <ControlPanel />
              <div className="space-y-6">
                <ExportConfig />
                <FilterConfig />
              </div>
            </div>
          </section>

          <section className="space-y-3">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                运行区
              </p>
              <h2 className="text-xl font-semibold tracking-tight">
                实时状态与结果回收
              </h2>
              <p className="max-w-3xl text-sm text-muted-foreground">
                运行进度、失败信号和结果下载都放在同一视区，避免状态分散。
              </p>
            </div>
            <div className="grid gap-6 2xl:grid-cols-[minmax(0,1.25fr)_360px]">
              <StatusPanel />
              <ResultList />
            </div>
          </section>

          <section className="space-y-3">
            <div className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                参考区
              </p>
              <h2 className="text-xl font-semibold tracking-tight">
                知识能力与智能预览
              </h2>
              <p className="max-w-3xl text-sm text-muted-foreground">
                这些信息对运营判断有帮助，但不应阻塞主操作流，因此下沉到参考区。
              </p>
            </div>
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
              <KnowledgeOverview />
              <IntelligencePanel />
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
