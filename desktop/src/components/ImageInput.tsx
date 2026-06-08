interface ImageInputProps {
  imagePath: string;
  onPathChange: (path: string) => void;
  onBrowse: () => void;
  onStart: () => void;
  isDisabled: boolean;
}

export function ImageInput({
  imagePath,
  onPathChange,
  onBrowse,
  onStart,
  isDisabled,
}: ImageInputProps) {
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

        <button onClick={onStart} disabled={isDisabled}>
          {isDisabled ? "Job running..." : "Start job"}
        </button>
      </div>
    </div>
  );
}
