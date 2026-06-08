import { convertFileSrc } from "@tauri-apps/api/core";
import { FinalArtifact } from "../types";
import { ErrorDisplay } from "./ErrorDisplay";

interface ArtifactPreviewProps {
  artifacts: FinalArtifact[];
  isLoadingArtifacts: boolean;
  artifactsError: string;
}

export function ArtifactPreview({
  artifacts,
  isLoadingArtifacts,
  artifactsError,
}: ArtifactPreviewProps) {
  const previewImages = artifacts.filter((a) => a.previewable);
  const nonPreviewFiles = artifacts.filter((a) => !a.previewable);

  return (
    <section className="preview-card">
      <h2>Final Output Preview</h2>

      {isLoadingArtifacts && <p>Loading final artifacts...</p>}

      {artifactsError && (
        <ErrorDisplay label="Preview Error" message={artifactsError} />
      )}

      {!isLoadingArtifacts && !artifactsError && (
        <>
          {previewImages.length > 0 ? (
            <div className="preview-grid">
              {previewImages.map((file) => (
                <figure key={file.abs_path} className="preview-item">
                  <img
                    src={convertFileSrc(file.abs_path)}
                    alt={file.name}
                    loading="lazy"
                  />
                  <figcaption>{file.name}</figcaption>
                </figure>
              ))}
            </div>
          ) : (
            <p>No PNG previews were found in the final directory.</p>
          )}

          {nonPreviewFiles.length > 0 && (
            <div className="artifact-list">
              <h3>Other files</h3>
              <ul>
                {nonPreviewFiles.map((file) => (
                  <li key={file.abs_path}>
                    {file.name} ({file.ext})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
