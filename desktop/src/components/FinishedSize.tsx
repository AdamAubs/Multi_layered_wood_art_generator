import { useEffect, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { FrameShape } from "../types";

interface Props {
  imagePath: string;
  value: string | null;
  onChange: (value: string | null) => void;
  margin: number;
  shape: FrameShape;
  disabled: boolean;
}

export function FinishedSize({ imagePath, value, onChange, margin, shape, disabled }: Props) {
  const [source, setSource] = useState<{ path: string; width: number; height: number } | null>(null);
  const [errorPath, setErrorPath] = useState("");
  const [unit, setUnit] = useState<"in" | "mm">("in");
  const [locked, setLocked] = useState(true);
  const [draft, setDraft] = useState<[string, string]>(["", ""]);
  const image = source?.path === imagePath ? source : null;
  const factor = unit === "in" ? 25.4 : 1;
  const selected = value?.split("x").map(Number);
  const valid = selected?.length === 2 && selected.every(n => Number.isFinite(n) && n > 0);
  const outer = valid ? selected!.map(n => n * 25.4) : value === null && image
    ? [image.width * 25.4 / 300 + 2 * margin, image.height * 25.4 / 300 + 2 * margin] : null;
  const inner = outer?.map(n => n - 2 * margin);
  const drawable = inner && inner.every(n => n > 0);
  const stretched = shape === "rectangle" && image && drawable &&
    Math.abs((inner![0] / inner![1]) / (image.width / image.height) - 1) > 0.001;
  const format = (mm: number) => (mm / factor).toFixed(unit === "in" ? 2 : 1);

  useEffect(() => {
    let active = true;
    if (!imagePath.trim()) return;
    const img = new Image();
    img.onload = () => { if (active) setSource({ path: imagePath, width: img.naturalWidth, height: img.naturalHeight }); };
    img.onerror = () => { if (active) setErrorPath(imagePath); };
    img.src = convertFileSrc(imagePath.trim());
    return () => { active = false; };
  }, [imagePath]);

  useEffect(() => {
    const values = value?.split("x").map(Number);
    if (values?.length === 2 && values.every(n => Number.isFinite(n) && n > 0)) {
      setDraft(values.map(n => String(Number((n * 25.4 / factor).toFixed(4)))) as [string, string]);
    } else if (value === null) setDraft(["", ""]);
  }, [value, factor]);

  // Reapply the lock when the source or margin changes; typing is handled by edit.
  useEffect(() => {
    if (!locked || shape !== "rectangle" || !image || !valid || !selected) return;
    const width = selected[0] * 25.4;
    if (width <= 2 * margin) return;
    const height = (2 * margin + (width - 2 * margin) * image.height / image.width) / 25.4;
    if (Math.abs(height - selected[1]) > 0.000001) onChange(`${selected[0]}x${height}`);
  }, [margin, image?.width, image?.height, locked, shape]);

  function edit(axis: number, raw: string) {
    const next: [string, string] = [...draft];
    next[axis] = raw;
    const mm = Number(raw) * factor;
    if (locked && shape === "rectangle" && image && mm > 2 * margin) {
      const ratio = axis === 0 ? image.height / image.width : image.width / image.height;
      next[1 - axis] = String(Number(((2 * margin + (mm - 2 * margin) * ratio) / factor).toFixed(4)));
    }
    setDraft(next);
    onChange(next.every(n => n.trim() && Number(n) > 0 && Number.isFinite(Number(n)))
      ? next.map(n => Number(n) * factor / 25.4).join("x") : "");
  }

  return <section className="finished-size" aria-label="Finished dimensions">
    <div className="section-heading">
      <h3>{shape === "rectangle" ? "Finished outer size, including frame" : "Maximum outer size, including frame"}</h3>
      <p>Choose the size of your wood art before running the pipeline.</p>
    </div>
    <div className="size-controls">
      {(["Width", "Height"] as const).map((label, axis) => <label className="parameter-field" key={label}>
        <span>{label}</span>
        <input type="number" min="0" step="any" value={draft[axis]} disabled={disabled}
          placeholder={outer ? format(outer[axis]) : label} onChange={e => edit(axis, e.currentTarget.value)} />
      </label>)}
      <label className="parameter-field"><span>Units</span><select value={unit} disabled={disabled}
        onChange={e => setUnit(e.currentTarget.value as "in" | "mm")}><option value="in">Inches</option><option value="mm">Millimeters</option></select></label>
    </div>
    {shape === "rectangle" && <label className="toggle-field"><input type="checkbox" checked={locked} disabled={disabled}
      onChange={e => { setLocked(e.currentTarget.checked); if (e.currentTarget.checked && draft[0] && image) {
        const width = Number(draft[0]) * factor;
        if (width > 2 * margin) onChange(`${width / 25.4}x${(2 * margin + (width - 2 * margin) * image.height / image.width) / 25.4}`);
      } }} /><span>Keep artwork proportions when editing dimensions</span></label>}
    <button className="secondary-button" disabled={disabled} onClick={() => onChange(null)}>Reset to calculated default</button>
    {value === null && <p>Default uses 300 pixels per inch plus the frame margin. Enter a width or height to choose your own size.</p>}
    {value !== null && !valid && <p className="field-error">Enter positive width and height values.</p>}
    {image ? <>
      <p>Source image: {image.width} × {image.height} pixels</p>
      {outer && drawable && <>
        <div className="size-diagram">
          <div className="dimension-width">↔ {format(outer[0])} {unit}</div>
          <div className="dimension-height">↕ {format(outer[1])} {unit}</div>
          <div className="size-frame" style={{ aspectRatio: `${outer[0]} / ${outer[1]}`, maxWidth: `${Math.min(340, 420 * outer[0] / outer[1])}px`, margin: "auto" }}>
            <img src={convertFileSrc(imagePath.trim())} alt="Artwork positioned within the outer frame"
              style={{ left: `${margin / outer[0] * 100}%`, top: `${margin / outer[1] * 100}%`,
                width: `${inner![0] / outer[0] * 100}%`, height: `${inner![1] / outer[1] * 100}%`,
                objectFit: shape === "rectangle" ? "fill" : "contain" }} />
          </div>
        </div>
        <p aria-live="polite"><strong>{shape === "rectangle" ? "Finished outer size" : value === null ? "Estimated outer bounds" : "Maximum outer size"}: {format(outer[0])} × {format(outer[1])} {unit}</strong></p>
        {shape === "rectangle" && <p>Artwork area: {format(inner![0])} × {format(inner![1])} {unit}. Frame margin: {margin.toFixed(1)} mm on each side.</p>}
      </>}
      {stretched && <p className="field-warning">These dimensions stretch the artwork to fill the inner frame. Edit a dimension with proportions locked to preserve its shape.</p>}
      <details><summary>Resolution details</summary><p>The source pixels stay unchanged. Size controls scale the cutting files.</p>
        {drawable && shape === "rectangle" && <p>Effective resolution: {(image.width * 25.4 / inner![0]).toFixed(1)} PPI horizontally, {(image.height * 25.4 / inner![1]).toFixed(1)} PPI vertically.</p>}
      </details>
    </> : <p>{errorPath === imagePath && imagePath ? "Unable to preview this image. Check the file path and format." : "Choose an image to preview its dimensions."}</p>}
    {shape === "first_layer" && <p>The preview shows a bounding box, not the traced outline. The finished shape preserves proportions; one dimension may be smaller. Exact bounds are measured after generation. If artwork reaches the source boundary, the pipeline uses a rectangular frame and reports the change.</p>}
  </section>;
}
