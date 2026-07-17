import { useEffect, useState } from "react";
import { useJob } from "./hooks/useJob";
import { useArtifacts } from "./hooks/useArtifacts";
import { useImagePath } from "./hooks/useImagePath";
import { useProjects } from "./hooks/useProjects";
import { isRunningStatus } from "./utils/statusHelpers";
import { PipelineInput } from "./components/PipelineInput";
import { JobStatus } from "./components/JobStatus";
import { ArtifactPreview } from "./components/ArtifactPreview";
import { TemplateLibraryPage } from "./components/TemplateLibraryPage";
import "./App.css";

type Page = "generator" | "library";

function App() {
  const [page, setPage] = useState<Page>("generator");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [newProjectTitle, setNewProjectTitle] = useState("");
  const [runPromptDraft, setRunPromptDraft] = useState("");

  const { imagePath, setImagePath, browseForImage } = useImagePath();
  const { job, uiError, startJob } = useJob();
  const { artifacts, artifactsError, isLoadingArtifacts } = useArtifacts(job);

  const {
    projects,
    isLoadingProjects,
    isCreatingProject,
    projectsError,
    refreshProjects,
    createProject,
  } = useProjects();

  useEffect(() => {
    refreshProjects().catch(() => {});
  }, [refreshProjects]);

  const isRunning = job ? isRunningStatus(job.status) : false;

  async function handleCreateProject() {
    try {
      const created = await createProject(newProjectTitle);
      setSelectedProjectId(created.projectId);
      setNewProjectTitle("");
    } catch {
      // projectsError is set in hook
    }
  }

  return (
    <main className="container">
      {page === "generator" ? (
        <>
          <h1>Multi-layered Wood Art Generator</h1>
          <div className="page-nav">
            <button onClick={() => setPage("library")}>
              Go To Prompt Library
            </button>
          </div>

          <PipelineInput
            selectedProjectId={selectedProjectId}
            onSelectProjectId={setSelectedProjectId}
            projects={projects}
            isLoadingProjects={isLoadingProjects}
            isCreatingProject={isCreatingProject}
            projectsError={projectsError}
            newProjectTitle={newProjectTitle}
            onNewProjectTitleChange={setNewProjectTitle}
            onCreateProject={handleCreateProject}
            onRefreshProjects={refreshProjects}
            imagePath={imagePath}
            onPathChange={setImagePath}
            onBrowse={browseForImage}
            promptValue={runPromptDraft}
            onPromptChange={setRunPromptDraft}
            onStart={(
              promptIn,
              stockSizeIn,
              bridgeCountIn,
              mergeVisibleFractionIn,
              omegaBudgetFactorIn,
            ) =>
              startJob(
                selectedProjectId,
                imagePath,
                promptIn,
                stockSizeIn,
                bridgeCountIn,
                mergeVisibleFractionIn,
                omegaBudgetFactorIn,
              )
            }
            isDisabled={isRunning}
          />

          <JobStatus job={job} uiError={uiError} />

          {job?.status === "complete" && (
            <ArtifactPreview
              artifacts={artifacts}
              isLoadingArtifacts={isLoadingArtifacts}
              artifactsError={artifactsError}
            />
          )}
        </>
      ) : (
        <TemplateLibraryPage onBackToGenerator={() => setPage("generator")} />
      )}
    </main>
  );
}

export default App;
