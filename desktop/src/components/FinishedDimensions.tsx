import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

type Report = { warnings?: string[]; frame_shape?: string; width_mm: number; height_mm: number; requested_size_in: string | null;
  layers: { file: string; width_mm: number; height_mm: number }[] };
const size = (w: number, h: number) => `${(w / 25.4).toFixed(2)} × ${(h / 25.4).toFixed(2)} in (${w.toFixed(1)} × ${h.toFixed(1)} mm)`;

export function FinishedDimensions({ finalDir }: { finalDir: string }) {
  const [state, setState] = useState<{ path: string; report?: Report | null; error?: string } | null>(null);
  useEffect(() => {
    let active = true;
    invoke<Report | null>("read_finished_dimensions", { finalDir }).then(report => {
      if (report && (!Number.isFinite(report.width_mm) || !Number.isFinite(report.height_mm) || !Array.isArray(report.layers))) throw new Error("Invalid dimension report");
      if (active) setState({ path: finalDir, report });
    }).catch(error => { if (active) setState({ path: finalDir, error: String(error) }); });
    return () => { active = false; };
  }, [finalDir]);
  const current = state?.path === finalDir ? state : null;
  return <section className="finished-size"><h3>Exported dimensions</h3>
    {!current ? <p>Reading measured dimensions…</p> : current.error ? <p className="field-error">{current.error}</p> : current.report ? <>
      <p><strong>{size(current.report.width_mm, current.report.height_mm)}</strong></p>
      <p>Overall layer bounds, measured from exported cutting files.</p>
      <p>Exported frame: {current.report.frame_shape === "first_layer" ? "First-layer outline" : "Rectangle"}</p>
      {current.report.warnings?.map(warning => <p className="field-warning" key={warning}>{warning}</p>)}
      <p>Requested size: {current.report.requested_size_in ? `${current.report.requested_size_in.replace("x", " × ")} in` : "Calculated default"}</p>
      <details><summary>Individual layer dimensions</summary><ul>{current.report.layers.map(layer => <li key={layer.file}>{layer.file}: {size(layer.width_mm, layer.height_mm)}</li>)}</ul></details>
    </> : <p>This older run has no saved dimension report. Generate a new run to record measured dimensions.</p>}
  </section>;
}
