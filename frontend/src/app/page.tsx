import { Header } from "@/components/layout/Header";
import { SourcePanel } from "@/components/sources/SourcePanel";
import { FilterConfig } from "@/components/config/FilterConfig";
import { ExportConfig } from "@/components/config/ExportConfig";
import { ControlPanel } from "@/components/control/ControlPanel";
import { StatusPanel } from "@/components/control/StatusPanel";
import { ResultList } from "@/components/results/ResultList";

export default function Home() {
  return (
    <div className="flex flex-col h-screen bg-background overflow-hidden">
      <Header />

      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Left: Source selection panel */}
        <div className="w-[280px] shrink-0 flex flex-col overflow-hidden border-r">
          <SourcePanel />
        </div>

        {/* Right: Main dashboard - single scrollable area */}
        <main className="flex-1 overflow-y-auto scrollbar-hide min-w-0 min-h-0">
          <div className="p-6 space-y-6">
            {/* Row 1: Control Panel (prominent) */}
            <ControlPanel />

            {/* Row 2: Export + Filter side by side */}
            <div className="grid grid-cols-[320px_1fr] gap-6">
              <ExportConfig />
              <FilterConfig />
            </div>

            {/* Row 3: Status Panel */}
            <StatusPanel />

            {/* Row 4: Results */}
            <ResultList />
          </div>
        </main>
      </div>
    </div>
  );
}
