import { useEffect, useState, useRef } from "react";
import reactLogo from "./assets/react.svg";
import { invoke } from "@tauri-apps/api/core";
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

  async function fetchStatus() {
    const latest = await invoke<JobSnapshot>("get_job_status");
    setJob(latest);

    if (isTerminal(latest.status) && pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
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

  const isRunning = job ? isRunningStatus(job.status) : false;

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
    </main>
  );
}

export default App;
