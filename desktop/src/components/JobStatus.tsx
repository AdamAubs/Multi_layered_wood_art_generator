import { JobSnapshot } from "../types";
import { ErrorDisplay } from "./ErrorDisplay";

interface JobStatusProps {
  job: JobSnapshot | null;
  uiError: string;
}

export function JobStatus({ job, uiError }: JobStatusProps) {
  return (
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
      {job?.error && <ErrorDisplay label="Error" message={job.error} />}
      {uiError && <ErrorDisplay label="UI Error" message={uiError} />}
    </section>
  );
}
