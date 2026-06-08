import { useEffect, useState, useRef } from "react";
import reactLogo from "./assets/react.svg";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import "./App.css";

type JobStatus =
  | "idle"
  | "preprocessing"
  | "generating"
  | "postprocessing"
  | "complete"
  | "failed";

type JobSnapshot = {
  job_id: string;
  status: JobStatus;
  elapsed_sec: number;
  message: string;
  error: string | null;
  n_colors: number | null;
  palette: { id: number; rgb: [number, number, number] }[];
  current_layer: number | null;
  winner_history: { layer: number; color_id: number; patches: number }[];
  final_dir: string | null;
};

type FinalArtifact = {
  name: string;
  abs_path: string;
  ext: string;
  previewable: boolean;
  category: string;
};

function isRunningStatus(status: JobStatus) {
  return (
    status === "preprocessing" ||
    status === "generating" ||
    status === "postprocessing"
  );
}

function isTerminal(status: JobStatus) {
  return status === "complete" || status === "failed";
}

function App() {
  const [imagePath, setImagePath] = useState("");
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [uiError, setUiError] = useState("");
  const pollRef = useRef<number | null>(null);

  const [artifacts, setArtifacts] = useState<FinalArtifact[]>([]);
  const [artifactsError, setArtifactsError] = useState("");
  const [isLoadingArtifacts, setIsLoadiningArtifacts] = useState(false);

  async function fetchStatus() {
    const latest = await invoke<JobSnapshot>("get_job_status");
    setJob(latest);

    if (isTerminal(latest.status) && pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function fetchFinalArtifacts(finalDir: string) {
    setArtifactsError("");
    setIsLoadiningArtifacts(true);

    try {
      const files = await invoke<FinalArtifact[]>("list_final_artifacts", {
        finalDir,
      });
      setArtifacts(files);
    } catch (e) {
      setArtifacts([]);
      setArtifactsError(String(e));
    } finally {
      setIsLoadiningArtifacts(false);
    }
  }

  async function browseForImage() {
    const selected = await open({
      title: "Select a PNG image you want to turn into separate layers",
      multiple: false,
      filters: [{ name: "PNG Image", extensions: ["png"] }],
    });
    if (typeof selected === "string") {
      setImagePath(selected);
    }
  }

  async function startJob() {
    setUiError("");

    const trimmed = imagePath.trim();
    if (!trimmed) {
      setUiError("Please enter an image path first.");
      return;
    }

    try {
      const started = await invoke<JobSnapshot>("start_job", {
        imagePath: trimmed,
      });
      setJob(started);

      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }

      pollRef.current = window.setInterval(() => {
        fetchStatus().catch((e) => {
          setUiError(String(e));
        });
      }, 1000);
    } catch (e) {
      setUiError(String(e));
    }
  }

  useEffect(() => {
    fetchStatus().catch((e) => setUiError(String(e)));
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (job?.status === "complete" && job.final_dir) {
      fetchFinalArtifacts(job.final_dir).catch((e) =>
        setArtifactsError(String(e)),
      );
    }

    if (job?.status !== "complete") {
      setArtifacts([]);
      setArtifactsError("");
    }
  }, [job?.status, job?.final_dir]);

  const isRunning = job ? isRunningStatus(job.status) : false;

  const previewImages = artifacts.filter((a) => a.previewable);
  const nonPreviewFiles = artifacts.filter((a) => !a.previewable);

  return (
    <main className="container">
      <h1>Multi-layered Wood Art Generator</h1>

      <div className="start-container">
        <div className="input-container">
          <label>
            Image path
            <input
              value={imagePath}
              onChange={(e) => setImagePath(e.currentTarget.value)}
              placeholder="/absolute/path/to/image.png"
              disabled={isRunning}
            />
          </label>

          <button onClick={browseForImage} disabled={isRunning}>
            Browse...
          </button>

          <button onClick={startJob} disabled={isRunning}>
            {isRunning ? "Job running..." : "Start job"}
          </button>
        </div>
      </div>

      <section className="status-card">
        <p>
          <strong>Status:</strong> {job?.status ?? "idle"}
        </p>
        <p>
          <strong>Job ID:</strong> {job?.job_id ?? "none"}
        </p>
        <p>
          <strong>Elapsed:</strong> {job?.elapsed_sec ?? 0}s
        </p>
        <p>
          <strong>Message:</strong> {job?.message ?? "No job started yet."}
        </p>
        <p>
          <strong>Number of Colors chosen:</strong> {job?.n_colors ?? "N/A."}
        </p>
        <p>
          <strong>Color Palette :</strong>{" "}
          {job?.palette?.map((color) => (
            <span key={color.id} style={{ marginRight: "8px" }}>
              <span
                style={{
                  display: "inline-block",
                  width: "16px",
                  height: "16px",
                  backgroundColor: `rgb(${color.rgb[0]}, ${color.rgb[1]}, ${color.rgb[2]})`,
                  border: "1px solid #ccc",
                }}
              />
              {` ID: ${color.id}`}
            </span>
          ))}
        </p>
        <p>
          <strong>Final directory:</strong> {job?.final_dir ?? "N/A."}
        </p>
        {job?.error && (
          <p className="error-text">
            <strong>Error:</strong> {job.error}
          </p>
        )}

        {uiError && (
          <p className="error-text">
            <strong>UI Error: {uiError} </strong>{" "}
          </p>
        )}
      </section>

      {job?.status === "complete" && (
        <section className="preview-card">
          <h2>Final Output Preview</h2>

          {isLoadingArtifacts && <p>Loading final artifacts...</p>}

          {artifactsError && (
            <p className="error-text">
              <strong>Preview Error:</strong> {artifactsError}
            </p>
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
      )}
    </main>
  );
}

export default App;
