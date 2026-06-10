import { useState } from "react";

const STOCK_PRESETS = ["12x20", "8x12", "18x24", "24x48"];
const STOCK_SIZE_REGEX = /^\d+(\.\d+)?x\d+(\.\d+)?$/;

interface PipelineInputProps {
  imagePath: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
  onStart: (stockSizeIn: string | null) => void;
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
    !(isCustom && (customStock.length === 0 || customIsInvalid));

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
        </label>

        <button onClick={onBrowse} disabled={isDisabled}>
          Browse...
        </button>

        <div className="stock-input-container">
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
        </div>

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

        <button onClick={() => onStart(stockSizeValue)} disabled={!canStart}>
          {isDisabled ? "Job running..." : "Start job"}
        </button>
      </div>
    </div>
  );
}
