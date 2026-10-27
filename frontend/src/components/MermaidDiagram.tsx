import { useEffect, useId, useState } from "react";
import { useTheme } from "../lib/theme";

type Props = { code: string; description: string; title: string };

export function MermaidDiagram({ code, description, title }: Props) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const { dark } = useTheme();
  const id = `mmd-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    let alive = true;
    setFailed(false);
    import("mermaid")
      .then(async ({ default: mermaid }) => {
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "default" });
        const { svg } = await mermaid.render(id, code);
        if (alive) setSvg(svg);
      })
      .catch(() => {
        if (alive) {
          setSvg(null);
          setFailed(true);
        }
        document.getElementById(`d${id}`)?.remove(); // mermaid leaves an error node behind
      });
    return () => {
      alive = false;
    };
  }, [code, dark, id]);

  return (
    <figure className="card p-4">
      {svg && !failed ? (
        <div
          role="img"
          aria-label={`${title}. ${description}`}
          className="overflow-x-auto flex justify-center [&_svg]:max-w-full [&_svg]:h-auto"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : failed ? (
        <p className="text-sm muted">The diagram could not be rendered. Text description below.</p>
      ) : (
        <p className="text-sm muted" role="status">Rendering diagram…</p>
      )}
      <figcaption className="mt-3 text-sm">
        <span className="font-semibold">Diagram description: </span>
        {description}
      </figcaption>
    </figure>
  );
}
