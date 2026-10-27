import { useEffect, useState } from "react";
import type { HighlighterGeneric } from "shiki";
import type { CodeExample } from "../schemas";

type Highlighter = HighlighterGeneric<"cpp" | "python", "github-light" | "github-dark">;
let highlighter: Promise<Highlighter> | null = null;

function getHighlighter(): Promise<Highlighter> {
  if (!highlighter) {
    highlighter = import("shiki").then(
      (m) => m.createHighlighter({ themes: ["github-light", "github-dark"], langs: ["cpp", "python"] }) as Promise<Highlighter>,
    );
  }
  return highlighter;
}

export function VerifiedBadge({ check }: { check: CodeExample["check"] }) {
  const ok = check.status === "verified";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold"
      style={{ color: ok ? "var(--strong)" : "var(--partial)", background: ok ? "var(--strong-bg)" : "var(--partial-bg)" }}
      title={check.tool}
    >
      <span aria-hidden>{ok ? "✓" : "!"}</span>
      {ok ? "Verified" : "Not verified"}
    </span>
  );
}

export function CodeBlock({ example }: { example: CodeExample }) {
  const [html, setHtml] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [showDetail, setShowDetail] = useState(false);

  useEffect(() => {
    let alive = true;
    getHighlighter()
      .then((h) => {
        const out = h.codeToHtml(example.code, {
          lang: example.language,
          themes: { light: "github-light", dark: "github-dark" },
          defaultColor: "light",
        });
        if (alive) setHtml(out);
      })
      .catch(() => alive && setHtml(null));
    return () => {
      alive = false;
    };
  }, [example.code, example.language]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(example.code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <figure className="card overflow-hidden">
      <figcaption className="flex flex-wrap items-center gap-2 px-4 py-2 border-b" style={{ borderColor: "var(--border)" }}>
        <span className="font-semibold text-sm">{example.title}</span>
        <span className="text-xs muted">{example.language === "cpp" ? "C++17" : "Python 3.10+"}{example.runnable ? " · runnable" : ""}</span>
        <span className="ml-auto flex items-center gap-2">
          <VerifiedBadge check={example.check} />
          <button className="btn-ghost text-xs no-print" onClick={copy} aria-label={`Copy code: ${example.title}`}>
            {copied ? "Copied" : "Copy"}
          </button>
        </span>
      </figcaption>
      <div className="overflow-x-auto text-[13px] leading-relaxed p-4" style={{ background: "var(--surface-2)" }}>
        {html ? (
          <div dangerouslySetInnerHTML={{ __html: html }} />
        ) : (
          <pre><code>{example.code}</code></pre>
        )}
      </div>
      <div className="px-4 py-3 text-sm space-y-2">
        <p>{example.explanation}</p>
        {example.check.status === "not_verified" && (
          <div className="text-xs">
            <button className="underline muted" onClick={() => setShowDetail((v) => !v)} aria-expanded={showDetail}>
              Why not verified?
            </button>
            {showDetail && (
              <pre className="mt-2 whitespace-pre-wrap rounded p-2 muted" style={{ background: "var(--surface-2)" }}>
                {check(example)}
              </pre>
            )}
          </div>
        )}
      </div>
    </figure>
  );
}

const check = (e: CodeExample) => `${e.check.tool}\n${e.check.detail ?? ""}`.trim();
