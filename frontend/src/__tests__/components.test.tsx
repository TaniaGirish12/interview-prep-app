import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { CodeBlock } from "../components/CodeBlock";
import { Markdown } from "../components/Markdown";
import { MatrixTable } from "../components/MatrixTable";
import { MermaidDiagram } from "../components/MermaidDiagram";
import { RevealAnswer } from "../components/RevealAnswer";
import { Analysis, type CodeExample } from "../schemas";

vi.mock("shiki", () => ({ createHighlighter: () => new Promise(() => {}) }));
vi.mock("mermaid", () => ({
  default: { initialize: vi.fn(), render: vi.fn().mockRejectedValue(new Error("Parse error")) },
}));

const analysis = Analysis.parse(
  JSON.parse(readFileSync(resolve(__dirname, "../../../shared/contract-fixtures/analysis.json"), "utf8")),
);
const result = analysis.result!;

function renderMatrix() {
  return render(<MemoryRouter><MatrixTable result={result} analysisId={1} /></MemoryRouter>);
}

describe("MatrixTable", () => {
  it("filters by status", async () => {
    renderMatrix();
    const total = result.jd_items.length;
    expect(screen.getByText(`${total} of ${total} requirements`)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Status"), "gap");
    const gaps = Object.values(result.matches).filter((m) => m.status === "gap").length;
    expect(screen.getByText(`${gaps} of ${total} requirements`)).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    rows.forEach((r) => expect(within(r).getByText("Gap")).toBeInTheDocument());
  });

  it("sorts by tier and toggles direction", async () => {
    renderMatrix();
    const tierHeader = screen.getByRole("columnheader", { name: /Tier/ });
    expect(tierHeader).toHaveAttribute("aria-sort", "ascending");
    const firstTier = () => within(screen.getAllByRole("row")[1]).getByText(/^Tier \d$/).textContent;
    expect(firstTier()).toBe("Tier 1");
    await userEvent.click(within(tierHeader).getByRole("button"));
    expect(tierHeader).toHaveAttribute("aria-sort", "descending");
    expect(firstTier()).toBe("Tier 4");
  });

  it("expands a row to show the JD quote and resume evidence", async () => {
    renderMatrix();
    const item = result.jd_items[0];
    await userEvent.click(screen.getByRole("button", { name: `Expand ${item.id}` }));
    expect(screen.getByText(new RegExp(item.quote.slice(0, 30).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).toBeInTheDocument();
    expect(screen.getByText("Resume evidence")).toBeInTheDocument();
  });
});

const example: CodeExample = {
  language: "cpp", title: "Lock guard", code: "int main() { return 0; }", runnable: true,
  explanation: "Minimal program.", jd_ids: ["JD-T02"],
  check: { status: "not_verified", tool: "g++ -fsyntax-only", detail: "error: something" },
};

describe("CodeBlock", () => {
  it("shows the verification badge and the failure detail", async () => {
    render(<CodeBlock example={example} />);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText("int main() { return 0; }")).toBeInTheDocument(); // plain fallback before Shiki loads
    await userEvent.click(screen.getByRole("button", { name: "Why not verified?" }));
    expect(screen.getByText(/error: something/)).toBeInTheDocument();
  });

  it("copies the code", async () => {
    const user = userEvent.setup();
    render(<CodeBlock example={{ ...example, check: { status: "verified", tool: "g++", detail: null } }} />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Copy code: Lock guard" }));
    expect(await navigator.clipboard.readText()).toBe(example.code);
    expect(screen.getByRole("button", { name: "Copy code: Lock guard" })).toHaveTextContent("Copied");
  });
});

describe("RevealAnswer", () => {
  it("hides the answer until revealed, keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<RevealAnswer><p>The model answer</p></RevealAnswer>);
    const button = screen.getByRole("button", { name: "Show model answer" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("The model answer")).not.toBeVisible();
    button.focus();
    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("The model answer")).toBeVisible();
  });
});

describe("MermaidDiagram", () => {
  it("falls back to the text description when rendering fails", async () => {
    render(<MermaidDiagram code="not mermaid" description="Thread A locks before B." title="Locking" />);
    await waitFor(() => expect(screen.getByText(/could not be rendered/)).toBeInTheDocument());
    expect(screen.getByText("Thread A locks before B.")).toBeInTheDocument();
  });
});

describe("Markdown", () => {
  it("renders lists and inline code without raw HTML", () => {
    const { container } = render(<Markdown text={"Intro with `std::mutex`.\n\n- one\n- **two**\n\n<script>alert(1)</script>"} />);
    expect(container.querySelector("code")?.textContent).toBe("std::mutex");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("script")).toBeNull();
  });
});
