// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
use serde::Serialize;
use std::path::PathBuf;
use std::process::Command;
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

// Derive adds auo-generated implementations: Debug print, Clone copy-by-value, etc.
#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]

// Serialize enum values as snake_case string in JSON: "preprocessing", "complete", etc.
#[serde(rename_all = "snake_case")]
enum JobStatus {
    Idle,
    Preprocessing,
    Generating,
    Postprocessing,
    Complete,
    Failed,
}

// Internal backend state (not serialized directly to frontend)
#[derive(Debug, Clone)]
struct JobState {
    job_id: String,
    status: JobStatus,
    started_at: Instant,
    message: String,
    error: Option<String>,
}

// Snapshot sent to frontend polling call.
#[derive(Debug, Clone, Serialize)]
struct JobSnapshot {
    job_id: String,
    status: JobStatus,
    elapsed_sec: u64,
    message: String,
    error: Option<String>
}

// Global singleton store: one job at a time, wrapped in Mutex for thread safety.
static JOB_STATE: OnceLock<Mutex<Option<JobState>>> = OnceLock::new();

// Helper that return global store, initializing it once.
fn job_store() -> &'static Mutex<Option<JobState>> {
    JOB_STATE.get_or_init(|| Mutex::new(None))
}

// Helper: terminal states where no further updates are expected
fn is_terminal(status: JobStatus) -> bool {
    matches!(status, JobStatus::Complete | JobStatus::Failed)
}


// Helper: milliseconds since Unix epoch, used to build a simple unique-ish id. 
fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

// Convert internal state to frontend-safe snapshot.
fn snapshot_from_state(state: &JobState) -> JobSnapshot {
    JobSnapshot {
        job_id: state.job_id.clone(),
        status: state.status,
        elapsed_sec: state.started_at.elapsed().as_secs(),
        message: state.message.clone(),
        error: state.error.clone(),
    }
}


// Expose this function as a Tauri command callable from frontend
#[tauri::command]
fn start_job(image_path: String) -> Result<JobSnapshot, String> {
    // Trim whitespace
    let trimmed = image_path.trim().to_string();

    // Validate non-empty path.
    if trimmed.is_empty() {
        return Err("Please choose an image path first.".to_string());
    }

    // Validate that file exists.
    let image = PathBuf::from(&trimmed);
    if !image.is_file() {
        return Err(format!("Image path does not exist: {trimmed}"));
    }    

    // Lock global job store; map lock poisoning to a user-friendly error
    let mut guard = job_store()
        .lock()
        .map_err(|_| "Failed to lock job state.".to_string())?;

    // Enforce single active job.
    if let Some(existing) = guard.as_ref() {
        if !is_terminal(existing.status) {
            return Err("A job is already running. Please wait for it to finish.".to_string());
        }
    }

    // Make job id
    let job_id = format!("job-{}", now_millis());

    let initial = JobState {
        job_id: job_id.clone(),
        status: JobStatus::Preprocessing,
        started_at: Instant::now(),
        message: "Pipeline started. Running preprocessor...".to_string(),
        error: None,
    };

    // Save initial state globally.
    *guard = Some(initial.clone());
    drop(guard);
    
    thread::spawn(move || {
        // Helper to update state safely in one place
        let update_state = |status: JobStatus, message: String, error: Option<String>| {
            if let Ok(mut g) = job_store().lock() {
                if let Some(state) = g.as_mut() {
                    if state.job_id == job_id {
                        state.status = status;
                        state.message = message;
                        state.error = error;
                    }
                }
            }
        };

        let repo_root = match PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
        {
            Ok(path) => path,
            Err(e) => {
                update_state(
                    JobStatus::Failed,
                    "Could not resolve repo root".to_string(),
                    Some(e.to_string()),
                );
                return;
            }
        };

        let python_path = repo_root.join("mwca_env/bin/python");
        if !python_path.is_file() {
            update_state(
                JobStatus::Failed,
                "Python interpreter not found.".to_string(),
                Some(format!(
                    "Expected interpreter at {}",
                    python_path.display()
                )),
            );
            return;
        }

        // Run pipeline process and wait for completion
        let output = match Command::new(&python_path)
            .arg("pipeline.py")
            .arg("--image")
            .arg(trimmed)
            .current_dir(&repo_root)
            .output()
        {
            Ok(o) => o,
            Err(e) => {
                update_state(
                    JobStatus::Failed,
                    "Failed to start pipeline process.".to_string(),
                    Some(e.to_string()),
                );
                return;
            }
        };

        // Update final status based on process exit code.
        if output.status.success() {
            update_state(
                JobStatus::Complete,
                "Pipeline finished successfully.".to_string(),
                None,
            );
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
            let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();

            let err = if !stderr.is_empty() {
                stderr
            } else if !stdout.is_empty() {
                stdout
            } else {
                "Pipeline failed without output.".to_string()
            };

            update_state(JobStatus::Failed, "Pipeline failed.".to_string(), Some(err));
        }
    });

    Ok(snapshot_from_state(&initial))
}

// Polling command for frontend
#[tauri::command]
fn get_job_status() -> Result<JobSnapshot, String> {
    let guard = job_store()
        .lock()
        .map_err(|_| "Failed to lock job state.".to_string())?;

    // If a job exists, return snapshot.
    if let Some(state) = guard.as_ref() {
        Ok(snapshot_from_state(state))
    } else {
        // Else return idle snapshot.
        Ok(JobSnapshot {
            job_id: "none".to_string(),
            status: JobStatus::Idle,
            elapsed_sec: 0,
            message: "No job has been started yet".to_string(),
            error: None,
        })
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![start_job, get_job_status])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
