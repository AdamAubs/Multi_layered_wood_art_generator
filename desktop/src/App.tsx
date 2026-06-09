import { useJob } from "./hooks/useJob";
import { useArtifacts } from "./hooks/useArtifacts";
import { useImagePath } from "./hooks/useImagePath";
import { isRunningStatus } from "./utils/statusHelpers";
import { PipelineInput } from "./components/PipelineInput";
import { JobStatus } from "./components/JobStatus";
import { ArtifactPreview } from "./components/ArtifactPreview";
import "./App.css";

function App() {
  const { imagePath, setImagePath, browseForImage } = useImagePath();
  const { job, uiError, startJob } = useJob();
  const { artifacts, artifactsError, isLoadingArtifacts } = useArtifacts(job);

  const isRunning = job ? isRunningStatus(job.status) : false;

  return (
    <main className="container">
      <h1>Multi-layered Wood Art Generator</h1>

      <PipelineInput
        imagePath={imagePath}
        onPathChange={setImagePath}
        onBrowse={browseForImage}
        onStart={(stockSizeIn) => startJob(imagePath, stockSizeIn)}
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
    </main>
  );
}

export default App;
