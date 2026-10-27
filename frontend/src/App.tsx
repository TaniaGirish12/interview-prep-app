import { useEffect, useState } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { ThemeToggle } from "./components/Widgets";
import { EmptyState, useLocalStorage } from "./components/ui";
import { AnalysisLayout } from "./pages/AnalysisLayout";
import { Company } from "./pages/Company";
import { Dashboard } from "./pages/Dashboard";
import { Flashcards } from "./pages/Flashcards";
import { Gaps } from "./pages/Gaps";
import { StudyPlan } from "./pages/StudyPlan";
import { Matrix } from "./pages/Matrix";
import { NewAnalysis } from "./pages/NewAnalysis";
import { Topic } from "./pages/Topic";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export function App() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Wide screens: the sidebar is docked and can be collapsed (remembered per browser).
  const [sidebarOpen, setSidebarOpen] = useLocalStorage("sidebarOpen", true);
  const location = useLocation();
  const wide = useMediaQuery("(min-width: 1024px)");
  const toggleSidebar = () => (wide ? setSidebarOpen(!sidebarOpen) : setDrawerOpen(true));

  useEffect(() => setDrawerOpen(false), [location.pathname]);
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:m-2 btn">Skip to content</a>
      <header className="sticky top-0 z-30 border-b no-print" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
        <div className="px-4 h-14 flex items-center gap-3">
          <button className="btn-ghost" onClick={toggleSidebar}
            aria-label={wide && sidebarOpen ? "Hide your interviews" : "Show your interviews"}
            aria-expanded={wide ? sidebarOpen : drawerOpen}
            aria-controls={wide ? "interviews-sidebar" : "interviews-drawer"}>
            <span aria-hidden>☰</span>
          </button>
          <Link to="/" className="font-bold">Interview Prep</Link>
          <span className="ml-auto" />
          <ThemeToggle />
        </div>
      </header>

      <div className="flex">
        <aside id="interviews-sidebar" className={`hidden ${sidebarOpen ? "lg:block" : ""} w-72 shrink-0 border-r no-print sticky top-14 h-[calc(100dvh-3.5rem)] overflow-y-auto p-4`}
          style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
          <Sidebar />
        </aside>

        {drawerOpen && (
          <div className="lg:hidden fixed inset-0 z-40 no-print" role="dialog" aria-modal="true" aria-label="Your interviews">
            <button className="absolute inset-0 bg-black/40 w-full" aria-label="Close interviews" onClick={() => setDrawerOpen(false)} />
            <div id="interviews-drawer" className="absolute inset-y-0 left-0 w-80 max-w-[85vw] overflow-y-auto p-4 shadow-xl"
              style={{ background: "var(--surface)" }}>
              <div className="flex items-center mb-3">
                <p className="font-semibold">Your interviews</p>
                <button className="btn-ghost ml-auto" onClick={() => setDrawerOpen(false)} aria-label="Close interviews">✕</button>
              </div>
              <Sidebar onNavigate={() => setDrawerOpen(false)} />
            </div>
          </div>
        )}

        <main id="main" className="min-w-0 flex-1">
          <div className="mx-auto max-w-6xl px-4 py-6 sm:py-8">
            <Routes>
              <Route path="/" element={<NewAnalysis />} />
              <Route path="/a/:id" element={<AnalysisLayout />}>
                <Route index element={<Dashboard />} />
                <Route path="matrix" element={<Matrix />} />
                <Route path="gaps" element={<Gaps />} />
                <Route path="plan" element={<StudyPlan />} />
                <Route path="cards" element={<Flashcards />} />
                <Route path="company" element={<Company />} />
                <Route path="topic/:jdId" element={<Topic />} />
              </Route>
              <Route path="*" element={<EmptyState title="Page not found"><Link className="underline" to="/">Start a new interview</Link></EmptyState>} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}
