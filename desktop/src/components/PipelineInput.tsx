import { useState } from "react";

const STOCK_PRESETS = ["12x20", "8x12", "18x24", "24x48"];
const STOCK_SIZE_REGEX = /^\d+(\.\d+)?x\d+(\.\d+)?$/;

const BRIDGE_PRESETS = ["3", "5", "8", "10", "12"];
const BRIDGE_COUNT_REGEX = /^\d+$/; // positive integer only

interface PipelineInputProps {
  imagePath: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
  onStart: (stockSizeIn: string | null, bridgeCountIn: number | null) => void;
  isDisabled: boolean;
}

export function PipelineInput({
  imagePath,
  onPathChange,
  onBrowse,
  onStart,
  isDisabled,
}: PipelineInputProps) {
  const [stockPreset, setStockPreset] = useState<string>("none");
  const [customStock, setCustomStock] = useState<string>("");

  const [bridgePreset, setBridgePreset] = useState<string>("5");
  const [customBridge, setCustomBridge] = useState<string>("");

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

  const isCustom = stockPreset === "other";
  const stockSizeValue = isCustom
    ? customStock
    : stockPreset === "none"
      ? null
      : stockPreset;
  const customIsInvalid =
    isCustom && customStock.length > 0 && !STOCK_SIZE_REGEX.test(customStock);
  const canStart =
    !isDisabled &&
    imagePath.trim().length > 0 &&
    !(isCustom && (customStock.length === 0 || customIsInvalid)) &&
    !(isBridgeCustom && (customBridge.length === 0 || bridgeCustomIsInvalid));

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
        </div>

        {bridgeWarning && (
          <div
            style={{ color: "#ff6b00", fontSize: "0.9em", marginTop: "6px" }}
          >
            ⚠ Note: High bridge counts may distort fine details. Consider values
            ≤10 for best results.
          </div>
        )}

        <button
          onClick={() => onStart(stockSizeValue, bridgeCountValue)}
          disabled={!canStart}
        >
          {isDisabled ? "Job running..." : "Start job"}
        </button>
      </div>
    </div>
  );
}
