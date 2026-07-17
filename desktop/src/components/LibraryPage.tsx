import { useEffect, useMemo, useState } from "react";
import { useLibrary } from "../hooks/useLibrary";
import { LibraryProjectEntry, LibraryRunEntry } from "../types";
import "../styles/library-page.css";

interface LibraryPageProps {
  onBackToGenerator: () => void;
}

function formatPromptStatus(saved: boolean): string {
  return saved ? "Saved" : "Not saved";
}

function statusLabel(status: string): string {
  if (status === "completed") return "Completed";
  if (status === "failed") return "Failed";
  if (status === "running") return "Running";
  if (status === "pending") return "Pending";
  return status;
}

export function LibraryPage({ onBackToGenerator }: LibraryPageProps) {
  const { projects, isLoading, error, refresh, openPath } = useLibrary();

  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    null,
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  useEffect(() => {
    if (projects.length === 0) {
      setSelectedProjectId(null);
      setSelectedRunId(null);
      return;
    }

    if (
      !selectedProjectId ||
      !projects.some((p) => p.project.projectId === selectedProjectId)
    ) {
      const firstProject = projects[0];
      setSelectedProjectId(firstProject.project.projectId);
      setSelectedRunId(firstProject.runs[0]?.run.runId ?? null);
      return;
    }

    const currentProject = projects.find(
      (p) => p.project.projectId === selectedProjectId,
    );
    if (!currentProject) return;

    if (
      !selectedRunId ||
      !currentProject.runs.some((r) => r.run.runId === selectedRunId)
    ) {
      setSelectedRunId(currentProject.runs[0]?.run.runId ?? null);
    }
  }, [projects, selectedProjectId, selectedRunId]);

  const selectedProject: LibraryProjectEntry | null = useMemo(
    () =>
      projects.find((p) => p.project.projectId === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );

  const selectedRun: LibraryRunEntry | null = useMemo(
    () =>
      selectedProject?.runs.find((r) => r.run.runId === selectedRunId) ?? null,
    [selectedProject, selectedRunId],
  );

  return (
    <section className="lib-page">
      <div className="lib-header">
        <h1>Library</h1>
        <div className="lib-header-actions">
          <button
            onClick={() => refresh().catch(() => {})}
            disabled={isLoading}
          >
            {isLoading ? "Refreshing..." : "Refresh"}
          </button>
          <button onClick={onBackToGenerator}>Back to Generator</button>
        </div>
      </div>

      {error && <p className="lib-error">{error}</p>}

      <div className="lib-grid">
        <aside className="lib-projects">
          <h2>Projects</h2>
          {projects.length === 0 && !isLoading && (
            <p>No projects found on disk.</p>
          )}
          <ul>
            {projects.map((entry) => (
              <li key={entry.project.projectId}>
                <button
                  className={
                    selectedProjectId === entry.project.projectId
                      ? "lib-active"
                      : ""
                  }
                  onClick={() => {
                    setSelectedProjectId(entry.project.projectId);
                    setSelectedRunId(entry.runs[0]?.run.runId ?? null);
                  }}
                >
                  {entry.project.title}
                  <span className="lib-muted">
                    {" "}
                    ({entry.project.projectId})
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section className="lib-runs">
          <h2>Runs</h2>
          {!selectedProject && <p>Select a project.</p>}
          {selectedProject && selectedProject.runs.length === 0 && (
            <p>No runs found for this project.</p>
          )}
          {selectedProject && selectedProject.runs.length > 0 && (
            <ul className="lib-run-list">
              {selectedProject.runs.map((entry) => (
                <li key={entry.run.runId} className="lib-run-card">
                  <button
                    className={
                      selectedRunId === entry.run.runId ? "lib-active" : ""
                    }
                    onClick={() => setSelectedRunId(entry.run.runId)}
                  >
                    <strong>{entry.run.runId}</strong>
                  </button>
                  <p>Status: {statusLabel(entry.run.status)}</p>
                  <p>Input: {entry.inputFilename}</p>
                  <p>Prompt: {formatPromptStatus(entry.promptSaved)}</p>
                  <p>Created: {entry.run.createdAt}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="lib-detail">
          <h2>Run Detail</h2>
          {!selectedRun && <p>Select a run to view details.</p>}

          {selectedRun && (
            <>
              <p>
                <strong>Run ID:</strong> {selectedRun.run.runId}
              </p>
              <p>
                <strong>Project:</strong> {selectedRun.run.projectId}
              </p>
              <p>
                <strong>Status:</strong> {statusLabel(selectedRun.run.status)}
              </p>
              <p>
                <strong>Input filename:</strong> {selectedRun.inputFilename}
              </p>
              <p>
                <strong>Prompt:</strong>{" "}
                {formatPromptStatus(selectedRun.promptSaved)}
              </p>

              <h3>Parameters</h3>
              <p>
                <strong>supportBridgesPerPatch:</strong>{" "}
                {selectedRun.run.parameters.supportBridgesPerPatch}
              </p>
              <p>
                <strong>mergeVisibleFraction:</strong>{" "}
                {String(selectedRun.run.parameters.mergeVisibleFraction)}
              </p>
              <p>
                <strong>omegaBudgetFactor:</strong>{" "}
                {String(selectedRun.run.parameters.omegaBudgetFactor)}
              </p>
              <p>
                <strong>generateCompositePreview:</strong>{" "}
                {String(selectedRun.run.parameters.generateCompositePreview)}
              </p>
              <p>
                <strong>generateShowcasePreview:</strong>{" "}
                {String(selectedRun.run.parameters.generateShowcasePreview)}
              </p>

              <h3>Output Paths</h3>
              <p>
                <strong>Generator:</strong> {selectedRun.run.outputs.generator}
              </p>
              <p>
                <strong>Postprocessed:</strong>{" "}
                {selectedRun.run.outputs.postprocessed}
              </p>
              <p>
                <strong>Final:</strong> {selectedRun.run.outputs.finalOutput}
              </p>
              <p>
                <strong>Runtime log:</strong> {selectedRun.run.runtimeLogPath}
              </p>

              <div className="lib-actions">
                <button onClick={() => openPath(selectedRun.runDirAbs)}>
                  Open Run Folder
                </button>
                <button onClick={() => openPath(selectedRun.finalOutputDirAbs)}>
                  Open Final Output Folder
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </section>
  );
}
