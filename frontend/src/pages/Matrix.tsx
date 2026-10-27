import { MatrixTable } from "../components/MatrixTable";
import { EmptyState } from "../components/ui";
import { useAnalysisCtx } from "./AnalysisLayout";

export function Matrix() {
  const { result, id } = useAnalysisCtx();
  if (!result.jd_items.length) return <EmptyState title="No requirements were extracted." />;
  return <MatrixTable result={result} analysisId={id} />;
}
