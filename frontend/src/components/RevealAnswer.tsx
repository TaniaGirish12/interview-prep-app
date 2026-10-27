import { useId, useState, type ReactNode } from "react";

export function RevealAnswer({ children, label = "Show model answer" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div>
      <button
        type="button"
        className="btn-ghost text-sm no-print"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide model answer" : label}
      </button>
      <div id={id} hidden={!open} className="print-reveal mt-3">
        {children}
      </div>
    </div>
  );
}
