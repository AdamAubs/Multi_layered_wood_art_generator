import { useState } from "react";

const STOCK_PRESETS = ["12x20", "8x12", "18x24", "24x48"];
const STOCK_SIZE_REGEX = /^\d+(\.\d+)?x\d+(\.\d+)?$/;

const BRIDGE_PRESETS = ["3", "5", "8", "10", "12"];
const BRIDGE_COUNT_REGEX = /^\d+$/; // positive integer only

const MERGE_PRESETS = ["0.01", "0.02", "0.03", "0.05", "0.1"];
const OMEGA_PRESETS = ["0.008", "0.01", "0.012", "0.02"];

const FRACTION_REGEX = /^(0?\.\d+)$/; // simple: 0.xx

interface PipelineInputProps {
  imagePath: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
  promptValue: string;
  onPromptChange: (value: string) => void;
  onPreparePromptForRun: (prompt: string | null) => void;
  onStart: (
    stockSizeIn: string | null,
    bridgeCountIn: number | null,
    mergeVisibleFractionIn: number | null,
    omegaBudgetFactorIn: number | null,
  ) => void;
  isDisabled: boolean;
}

export function PipelineInput({
  imagePath,
  onPathChange,
  onBrowse,
  promptValue,
  onPromptChange,
  onPreparePromptForRun,
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

  const canStart =
    !isDisabled &&
    imagePath.trim().length > 0 &&
    !(isCustom && (customStock.length === 0 || customIsInvalid)) &&
    !(isBridgeCustom && (customBridge.length === 0 || bridgeCustomIsInvalid)) &&
    !(isMergeCustom && (customMerge.length === 0 || mergeCustomIsInvalid));

  function handleStart() {
    const normalizedPrompt = promptValue.trim();
    onPreparePromptForRun(
      normalizedPrompt.length > 0 ? normalizedPrompt : null,
    );

    onStart(
      stockSizeValue,
      bridgeCountValue,
      mergeVisibleFractionValue,
      omegaBudgetFactorValue,
    );
  }

  return (
    <div className="start-container">
      <div className="input-container">
        <label>
          Image path
          <input
            value={imagePath}
            onChange={(e) => onPathChange(e.currentTarget.value)}
            placeholder="/absolute/path/to/image.png"
            disabled={isDisabled}
          />
          <button onClick={onBrowse} disabled={isDisabled}>
            Browse...
          </button>
        </label>

        <label>
          Image-generation prompt (optional)
          <textarea
            value={promptValue}
            onChange={(e) => onPromptChange(e.currentTarget.value)}
            placeholder="Paste the prompt used to create this image."
            rows={5}
            disabled={isDisabled}
          />
        </label>
        <p
          style={{ marginTop: "4px", marginBottom: "10px", fontSize: "0.9em" }}
        >
          This prompt is saved for future image and pipeline tuning. It is not
          required by the wood-art generator.
        </p>

        <div className="additional-options-container">
          <label>
            Stock size (inches)
            <select
              value={stockPreset}
              onChange={(e) => setStockPreset(e.currentTarget.value)}
              disabled={isDisabled}
            >
              <option value="none">None (default)</option>
              {STOCK_PRESETS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
              <option value="other">Other...</option>
            </select>
          </label>

          <div className="custom-size">
            {isCustom && (
              <label>
                Custom size (W x H)
                <input
                  value={customStock}
                  onChange={(e) => setCustomStock(e.currentTarget.value)}
                  placeholder="e.g. 10x16"
                  disabled={isDisabled}
                />
                {customIsInvalid && (
                  <span style={{ color: "red", fontSize: "0.8em" }}>
                    Format must be WxH (e.g. 12x20)
                  </span>
                )}
              </label>
            )}
          </div>

          <label>
            Support bridges per patch
            <select
              value={bridgePreset}
              onChange={(e) => setBridgePreset(e.currentTarget.value)}
              disabled={isDisabled}
            >
              {BRIDGE_PRESETS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
              <option value="other">Other...</option>
            </select>
          </label>

          <div className="custom-bridge">
            {isBridgeCustom && (
              <label>
                Custom bridge count
                <input
                  value={customBridge}
                  onChange={(e) => setCustomBridge(e.currentTarget.value)}
                  placeholder="e.g. 6"
                  disabled={isDisabled}
                />
                {bridgeCustomIsInvalid && (
                  <span style={{ color: "red", fontSize: "0.8em" }}>
                    Must be a positive whole number
                  </span>
                )}
              </label>
            )}
          </div>

          <div className="custom-bridge">
            <label>
              Merge visible fraction
              <select
                value={mergePreset}
                onChange={(e) => setMergePreset(e.currentTarget.value)}
                disabled={isDisabled}
              >
                {MERGE_PRESETS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
                <option value="other">Other...</option>
              </select>
            </label>

            {isMergeCustom && (
              <label>
                Custom merge fraction
                <input
                  value={customMerge}
                  onChange={(e) => setCustomMerge(e.currentTarget.value)}
                  placeholder="e.g. 0.03"
                  disabled={isDisabled}
                />
                {mergeCustomIsInvalid && (
                  <span style={{ color: "red", fontSize: "0.8em" }}>
                    Must be a decimal between 0 and 1 (e.g. 0.03)
                  </span>
                )}
              </label>
            )}
          </div>

          <div className="custom-bridge">
            <label>
              Omega budget factor
              <select
                value={omegaPreset}
                onChange={(e) => setOmegaPreset(e.currentTarget.value)}
                disabled={isDisabled}
              >
                {OMEGA_PRESETS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
                <option value="other">Other...</option>
              </select>
            </label>

            {isOmegaCustom && (
              <label>
                Custom omega factor
                <input
                  value={customOmega}
                  onChange={(e) => setCustomOmega(e.currentTarget.value)}
                  placeholder="e.g. 0.01"
                  disabled={isDisabled}
                />
                {omegaCustomIsInvalid && (
                  <span style={{ color: "red", fontSize: "0.8em" }}>
                    Must be a decimal between 0 and 1 (e.g. 0.01)
                  </span>
                )}
              </label>
            )}
          </div>
        </div>

        {bridgeWarning && (
          <div
            style={{ color: "#ff6b00", fontSize: "0.9em", marginTop: "6px" }}
          >
            ⚠ Note: High bridge counts may distort fine details. Consider values
            ≤10 for best results.
          </div>
        )}

        <button onClick={handleStart} disabled={!canStart}>
          {isDisabled ? "Job running..." : "Start job"}
        </button>
      </div>
    </div>
  );
}
