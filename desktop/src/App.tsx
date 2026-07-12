import { useJob } from "./hooks/useJob";
import { useArtifacts } from "./hooks/useArtifacts";
import { useImagePath } from "./hooks/useImagePath";
import { isRunningStatus } from "./utils/statusHelpers";
import { PipelineInput } from "./components/PipelineInput";
import { JobStatus } from "./components/JobStatus";
import { ArtifactPreview } from "./components/ArtifactPreview";
import { TemplateLibraryPage } from "./components/TemplateLibraryPage";
import "./App.css";
import { useState } from "react";

type Page = "generator" | "library";

function App() {
  const [page, setPage] = useState<Page>("generator");
  const [runPromptDraft, setRunPromptDraft] = useState("");
  const [, setPreparedPromptForNextRun] = useState<string | null>(null);

  const { imagePath, setImagePath, browseForImage } = useImagePath();
  const { job, uiError, startJob } = useJob();
  const { artifacts, artifactsError, isLoadingArtifacts } = useArtifacts(job);

  const isRunning = job ? isRunningStatus(job.status) : false;

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
            imagePath={imagePath}
            onPathChange={setImagePath}
            onBrowse={browseForImage}
            promptValue={runPromptDraft}
            onPromptChange={setRunPromptDraft}
            onPreparePromptForRun={setPreparedPromptForNextRun}
            onStart={(
              stockSizeIn,
              bridgeCountIn,
              mergeVisibleFractionIn,
              omegaBudgetFactorIn,
            ) =>
              startJob(
                imagePath,
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
