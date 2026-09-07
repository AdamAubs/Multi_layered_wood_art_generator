import { useState } from "react";
import { FinishedSize } from "./FinishedSize";
import { FrameShape, ProjectSummary } from "../types";

const STOCK_PRESETS = ["12x20", "8x12", "18x24", "24x48"];
const STOCK_SIZE_REGEX = /^\d+(\.\d+)?x\d+(\.\d+)?$/;

const BRIDGE_PRESETS = ["3", "5", "8", "10", "12"];
const BRIDGE_COUNT_REGEX = /^\d+$/;

const MERGE_PRESETS = ["0.01", "0.02", "0.03", "0.05", "0.1"];
const OMEGA_PRESETS = ["0.008", "0.01", "0.012", "0.02"];
const FRACTION_REGEX = /^(0?\.\d+)$/;
const POSITIVE_NUMBER_REGEX = /^(?:\d+(?:\.\d*)?|\.\d+)$/;

interface PipelineInputProps {
  selectedProjectId: string;
  onSelectProjectId: (value: string) => void;
  projects: ProjectSummary[];
  isLoadingProjects: boolean;
  isCreatingProject: boolean;
  projectsError: string;
  newProjectTitle: string;
  onNewProjectTitleChange: (value: string) => void;
  onCreateProject: () => void;
  onRefreshProjects: () => void;
  imagePath: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
  promptValue: string;
  onPromptChange: (value: string) => void;
  onStart: (
    promptIn: string | null,
    stockSizeIn: string | null,
    bridgeCountIn: number | null,
    mergeVisibleFractionIn: number | null,
    omegaBudgetFactorIn: number | null,
    fabSizeIn: string | null,
    frameShape: FrameShape,
    dxfFrameMarginMm: number,
    dxfSettingHoleDiameterMm: number,
    dxfSettingHoleInsetMm: number,
    addFrenchCleats: boolean,
    createEtsyRelease: boolean,
  ) => void;
  isDisabled: boolean;
}

export function PipelineInput({
  selectedProjectId,
  onSelectProjectId,
  projects,
  isLoadingProjects,
  isCreatingProject,
  projectsError,
  newProjectTitle,
  onNewProjectTitleChange,
  onCreateProject,
  onRefreshProjects,
  imagePath,
  onPathChange,
  onBrowse,
  promptValue,
  onPromptChange,
  onStart,
  isDisabled,
}: PipelineInputProps) {
  const [stockPreset, setStockPreset] = useState<string>("none");
  const [customStock, setCustomStock] = useState<string>("");

  const [bridgePreset, setBridgePreset] = useState<string>("5");
  const [customBridge, setCustomBridge] = useState<string>("");

  const [mergePreset, setMergePreset] = useState<string>("0.03");
  const [customMerge, setCustomMerge] = useState<string>("");

  const [omegaPreset, setOmegaPreset] = useState<string>("0.01");
  const [customOmega, setCustomOmega] = useState<string>("");

  const [outerFrameSizePreset, setOuterFrameSizePreset] =
    useState<string>("none");
  const [frameShape, setFrameShape] = useState<FrameShape>("rectangle");
  const [customOuterFrameSize, setCustomOuterFrameSize] = useState<string>("");
  const [frameMarginMm, setFrameMarginMm] = useState<string>("5");
  const [settingHoleDiameterMm, setSettingHoleDiameterMm] =
    useState<string>("2.5");
  const [settingHoleInsetMm, setSettingHoleInsetMm] = useState<string>("7");
  const [addFrenchCleats, setAddFrenchCleats] = useState(false);
  const [createEtsyRelease, setCreateEtsyRelease] = useState(false);

  const isCustom = stockPreset === "other";
  const stockSizeValue = isCustom
    ? customStock
    : stockPreset === "none"
      ? null
      : stockPreset;
  const customIsInvalid =
    isCustom && customStock.length > 0 && !STOCK_SIZE_REGEX.test(customStock);

  const isBridgeCustom = bridgePreset === "other";
  const bridgeCountValue = isBridgeCustom
    ? customBridge.length > 0
      ? parseInt(customBridge, 10)
      : null
    : parseInt(bridgePreset, 10);

  const bridgeCustomIsInvalid =
    isBridgeCustom &&
    customBridge.length > 0 &&
    !BRIDGE_COUNT_REGEX.test(customBridge);
  const bridgeWarning = bridgeCountValue !== null && bridgeCountValue > 10;

  const isMergeCustom = mergePreset === "other";
  const mergeRaw = isMergeCustom ? customMerge : mergePreset;
  const mergeVisibleFractionValue =
    mergeRaw.length > 0 ? parseFloat(mergeRaw) : null;
  const mergeCustomIsInvalid =
    isMergeCustom &&
    customMerge.length > 0 &&
    (!FRACTION_REGEX.test(customMerge) ||
      !(parseFloat(customMerge) > 0 && parseFloat(customMerge) < 1));

  const isOmegaCustom = omegaPreset === "other";
  const omegaRaw = isOmegaCustom ? customOmega : omegaPreset;
  const omegaBudgetFactorValue =
    omegaRaw.length > 0 ? parseFloat(omegaRaw) : null;
  const omegaCustomIsInvalid =
    isOmegaCustom &&
    customOmega.length > 0 &&
    (!FRACTION_REGEX.test(customOmega) ||
      !(parseFloat(customOmega) > 0 && parseFloat(customOmega) < 1));

  const isCustomOuterFrameSize = outerFrameSizePreset === "other";
  const outerFrameSizeValue = isCustomOuterFrameSize
    ? customOuterFrameSize
    : outerFrameSizePreset === "none"
      ? null
      : outerFrameSizePreset;
  const outerFrameSizeIsInvalid =
    isCustomOuterFrameSize &&
    customOuterFrameSize.length > 0 &&
    !(customOuterFrameSize.split("x").length === 2 && customOuterFrameSize.split("x").every(n => Number.isFinite(Number(n)) && Number(n) > 0));

  const parsePositiveNumber = (value: string) => {
    const parsed = Number(value);
    return POSITIVE_NUMBER_REGEX.test(value) &&
      Number.isFinite(parsed) &&
      parsed > 0
      ? parsed
      : null;
  };
  const frameMarginValue = parsePositiveNumber(frameMarginMm);
  const settingHoleDiameterValue = parsePositiveNumber(settingHoleDiameterMm);
  const settingHoleInsetValue = parsePositiveNumber(settingHoleInsetMm);
  const dxfGeometryIsInvalid =
    frameMarginValue === null ||
    settingHoleDiameterValue === null ||
    settingHoleInsetValue === null ||
    (settingHoleDiameterValue !== null &&
      settingHoleInsetValue !== null &&
      settingHoleInsetValue < settingHoleDiameterValue / 2);

  const outerFrameBoundsAreInvalid = (() => {
    if (
      outerFrameSizeValue === null ||
      outerFrameSizeIsInvalid ||
      frameMarginValue === null ||
      settingHoleDiameterValue === null ||
      settingHoleInsetValue === null
    ) {
      return false;
    }
    const [widthIn, heightIn] = outerFrameSizeValue
      .toLowerCase()
      .split("x")
      .map(Number);
    const widthMm = widthIn * 25.4;
    const heightMm = heightIn * 25.4;
    const holeRadiusMm = settingHoleDiameterValue / 2;
    const minimumShapedOffset = Math.max(
      frameMarginValue,
      settingHoleInsetValue + settingHoleDiameterValue + 0.5,
    );
    if (frameShape === "first_layer") {
      return (
        widthMm <= minimumShapedOffset * 2 ||
        heightMm <= minimumShapedOffset * 2
      );
    }
    return (
      widthMm <= frameMarginValue * 2 ||
      heightMm <= frameMarginValue * 2 ||
      settingHoleInsetValue + holeRadiusMm > Math.min(widthMm, heightMm)
    );
  })();

  const canStart =
    !isDisabled &&
    selectedProjectId.trim().length > 0 &&
    imagePath.trim().length > 0 &&
    !(isCustom && (customStock.length === 0 || customIsInvalid)) &&
    !(isBridgeCustom && (customBridge.length === 0 || bridgeCustomIsInvalid)) &&
    !(isMergeCustom && (customMerge.length === 0 || mergeCustomIsInvalid)) &&
    !(
      isCustomOuterFrameSize &&
      (customOuterFrameSize.length === 0 || outerFrameSizeIsInvalid)
    ) &&
    !dxfGeometryIsInvalid &&
    !outerFrameBoundsAreInvalid;

  function handleStart() {
    const normalizedPrompt = promptValue.trim();
    onStart(
      normalizedPrompt.length > 0 ? normalizedPrompt : null,
      stockSizeValue,
      bridgeCountValue,
      mergeVisibleFractionValue,
      omegaBudgetFactorValue,
      outerFrameSizeValue,
      frameShape,
      frameMarginValue!,
      settingHoleDiameterValue!,
      settingHoleInsetValue!,
      addFrenchCleats,
      createEtsyRelease,
    );
  }

  const selectedProjectTitle = projects.find(
    (project) => project.projectId === selectedProjectId,
  )?.title;

  return (
    <div className="start-container">
      <div className="input-container">
        <details className="project-dropdown" open>
          <summary>
            <span>Project</span>
            <span className="project-dropdown-value">
              {selectedProjectTitle ?? "Choose a project"}
            </span>
          </summary>
          <div className="project-fields">
            <label className="field-control">
              <span>Existing project</span>
              <select
                value={selectedProjectId}
                onChange={(e) => onSelectProjectId(e.currentTarget.value)}
                disabled={isDisabled || isLoadingProjects}
              >
                <option value="">Select existing project</option>
                {projects.map((project) => (
                  <option key={project.projectId} value={project.projectId}>
                    {project.title} ({project.projectId})
                  </option>
                ))}
              </select>
            </label>

            <label className="field-control">
              <span>New project title</span>
              <input
                value={newProjectTitle}
                onChange={(e) => onNewProjectTitleChange(e.currentTarget.value)}
                placeholder="e.g. Tomorrow Test"
                disabled={isDisabled || isCreatingProject}
              />
            </label>

            <div className="project-actions">
              <button
                onClick={onCreateProject}
                disabled={
                  isDisabled || isCreatingProject || !newProjectTitle.trim()
                }
              >
                {isCreatingProject ? "Creating..." : "Create project"}
              </button>
              <button
                className="secondary-button"
                onClick={onRefreshProjects}
                disabled={isDisabled || isLoadingProjects}
              >
                Refresh projects
              </button>
            </div>
          </div>
          {projectsError && <p className="field-error">{projectsError}</p>}
        </details>

        <section className="workflow-section">
          <div className="section-heading">
            <h2>Source artwork</h2>
            <p>Choose the image and optionally retain its generation prompt.</p>
          </div>
          <div className="source-fields">
            <label className="field-control source-file-field">
              <span>Image file</span>
              <div className="file-input-row">
                <input
                  value={imagePath}
                  onChange={(e) => onPathChange(e.currentTarget.value)}
                  placeholder="/absolute/path/to/image.png"
                  disabled={isDisabled}
                />
                <button
                  className="secondary-button"
                  onClick={onBrowse}
                  disabled={isDisabled}
                >
                  Browse
                </button>
              </div>
            </label>

            <label className="field-control source-prompt-field">
              <span>
                Image-generation prompt <em>(optional)</em>
              </span>
              <textarea
                value={promptValue}
                onChange={(e) => onPromptChange(e.currentTarget.value)}
                placeholder="Paste the prompt used to create this image."
                rows={4}
                disabled={isDisabled}
              />
              <small>
                Saved with the run for future image and pipeline tuning.
              </small>
            </label>
          </div>
        </section>

        <section className="workflow-section">
          <div className="section-heading">
            <h2>Fabrication</h2>
            <p>
              Set the physical frame, stock, mounting, and delivery options.
            </p>
          </div>
          <FinishedSize imagePath={imagePath} value={outerFrameSizeValue}
            onChange={value => { setOuterFrameSizePreset(value === null ? "none" : "other"); setCustomOuterFrameSize(value ?? ""); }}
            margin={frameShape === "first_layer" ? Math.max(frameMarginValue ?? 0, (settingHoleInsetValue ?? 0) + (settingHoleDiameterValue ?? 0) + 0.5) : frameMarginValue ?? 0}
            shape={frameShape} disabled={isDisabled} />
          <div className="parameter-grid fabrication-grid">
            <label className="parameter-field parameter-field-wide">
              <span>Frame shape</span>
              <select
                value={frameShape}
                onChange={(e) => setFrameShape(e.currentTarget.value as FrameShape)}
                disabled={isDisabled}
              >
                <option value="rectangle">Square/rectangle (current)</option>
                <option value="first_layer">First-layer outline</option>
              </select>
              <small>
                {frameShape === "first_layer"
                  ? "Uses the first enclosed trace. Make the background dominant so it is selected first."
                  : "Uses the current rectangular outer frame and corner holes."}
              </small>
            </label>

            <label className="parameter-field">
              <span>
                Stock sheet size <em>(inches, for cut layout)</em>
              </span>
              <select
                value={stockPreset}
                onChange={(e) => setStockPreset(e.currentTarget.value)}
                disabled={isDisabled}
              >
                <option value="none">None (default)</option>
                {STOCK_PRESETS.map((preset) => (
                  <option key={preset} value={preset}>
                    {preset}
                  </option>
                ))}
                <option value="other">Custom...</option>
              </select>
              {isCustom && (
                <input
                  value={customStock}
                  onChange={(e) => setCustomStock(e.currentTarget.value)}
                  placeholder="e.g. 10x16"
                  disabled={isDisabled}
                />
              )}
              {customIsInvalid && (
                <small className="field-error">Use WxH, such as 12x20.</small>
              )}
            </label>

            <label className="parameter-field parameter-field-wide">
              <span>
                DXF frame margin <em>(mm)</em>
              </span>
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={frameMarginMm}
                onChange={(e) => setFrameMarginMm(e.currentTarget.value)}
                disabled={isDisabled}
              />
              <small>
                {frameShape === "first_layer"
                  ? `Minimum outline offset. Hole clearance requires at least ${Math.max(
                      frameMarginValue ?? 0,
                      (settingHoleInsetValue ?? 0) +
                        (settingHoleDiameterValue ?? 0) +
                        0.5,
                    ).toFixed(1)} mm with the current hole settings.`
                  : "Exact space between the artwork contour and outer frame, not the final artwork size."}
              </small>
            </label>

            <label className="parameter-field">
              <span>
                Setting-hole diameter <em>(mm)</em>
              </span>
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={settingHoleDiameterMm}
                onChange={(e) =>
                  setSettingHoleDiameterMm(e.currentTarget.value)
                }
                disabled={isDisabled}
              />
            </label>

            <label className="parameter-field">
              <span>
                Setting-hole inset <em>(mm)</em>
              </span>
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={settingHoleInsetMm}
                onChange={(e) => setSettingHoleInsetMm(e.currentTarget.value)}
                disabled={isDisabled}
              />
              <small>
                {frameShape === "first_layer"
                  ? "Clearance from the first trace to the hole's nearest edge; one hole is placed per quadrant."
                  : "Measured from each outer frame corner."}
              </small>
            </label>

            <label className="toggle-field">
              <input
                type="checkbox"
                checked={addFrenchCleats}
                onChange={(e) => setAddFrenchCleats(e.currentTarget.checked)}
                disabled={isDisabled}
              />
              <span>
                <strong>Add French cleats</strong>
                <small>Add mounting layers after finalization.</small>
              </span>
            </label>

            <label className="toggle-field">
              <input
                type="checkbox"
                checked={createEtsyRelease}
                onChange={(e) => setCreateEtsyRelease(e.currentTarget.checked)}
                disabled={isDisabled}
              />
              <span>
                <strong>Create Etsy release</strong>
                <small>Build buyer files after a successful run.</small>
              </span>
            </label>
          </div>
        </section>

        <section className="workflow-section">
          <div className="section-heading">
            <h2>Layer behavior</h2>
            <p>Controls for support strength, merge tolerance, and detail.</p>
          </div>
          <div className="parameter-grid layer-grid">
            <label className="parameter-field">
              <span>Support bridges per patch</span>
              <select
                value={bridgePreset}
                onChange={(e) => setBridgePreset(e.currentTarget.value)}
                disabled={isDisabled}
              >
                {BRIDGE_PRESETS.map((preset) => (
                  <option key={preset} value={preset}>
                    {preset}
                  </option>
                ))}
                <option value="other">Custom...</option>
              </select>
              {isBridgeCustom && (
                <input
                  value={customBridge}
                  onChange={(e) => setCustomBridge(e.currentTarget.value)}
                  placeholder="e.g. 6"
                  disabled={isDisabled}
                />
              )}
              {bridgeCustomIsInvalid && (
                <small className="field-error">
                  Use a positive whole number.
                </small>
              )}
            </label>

            <label className="parameter-field">
              <span>Merge visible fraction</span>
              <select
                value={mergePreset}
                onChange={(e) => setMergePreset(e.currentTarget.value)}
                disabled={isDisabled}
              >
                {MERGE_PRESETS.map((preset) => (
                  <option key={preset} value={preset}>
                    {preset}
                  </option>
                ))}
                <option value="other">Custom...</option>
              </select>
              {isMergeCustom && (
                <input
                  value={customMerge}
                  onChange={(e) => setCustomMerge(e.currentTarget.value)}
                  placeholder="e.g. 0.03"
                  disabled={isDisabled}
                />
              )}
              {mergeCustomIsInvalid && (
                <small className="field-error">
                  Use a decimal between 0 and 1.
                </small>
              )}
            </label>

            <label className="parameter-field">
              <span>Omega budget factor</span>
              <select
                value={omegaPreset}
                onChange={(e) => setOmegaPreset(e.currentTarget.value)}
                disabled={isDisabled}
              >
                {OMEGA_PRESETS.map((preset) => (
                  <option key={preset} value={preset}>
                    {preset}
                  </option>
                ))}
                <option value="other">Custom...</option>
              </select>
              {isOmegaCustom && (
                <input
                  value={customOmega}
                  onChange={(e) => setCustomOmega(e.currentTarget.value)}
                  placeholder="e.g. 0.01"
                  disabled={isDisabled}
                />
              )}
              {omegaCustomIsInvalid && (
                <small className="field-error">
                  Use a decimal between 0 and 1.
                </small>
              )}
            </label>
          </div>
        </section>

        <div className="run-actions">
          <div>
            {bridgeWarning && (
              <p className="field-warning">
                High bridge counts can distort fine details. Values up to 10 are
                usually more reliable.
              </p>
            )}
            {(dxfGeometryIsInvalid || outerFrameBoundsAreInvalid) && (
              <p className="field-error">
                DXF geometry must use positive values, keep setting holes inside
                the frame, and leave room for the selected frame margin.
              </p>
            )}
          </div>
          <button onClick={handleStart} disabled={!canStart}>
            {isDisabled ? "Job running..." : "Start job"}
          </button>
        </div>
      </div>
    </div>
  );
}
