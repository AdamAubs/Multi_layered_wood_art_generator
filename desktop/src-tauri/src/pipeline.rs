use std::io::BufRead;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::thread;

use crate::log_tail::try_load_palette;
use crate::state::{job_store, is_terminal, set_status, set_message, set_final_dir, now_millis};
use crate::types::{JobState, JobStatus};

#[tauri::command]
pub fn start_job(image_path: String, stock_size_in: Option<String>) -> Result<crate::types::JobSnapshot, String> {
    let trimmed = image_path.trim().to_string();

    if trimmed.is_empty() {
        return Err("Please choose an image path first.".to_string());
    }
    if !PathBuf::from(&trimmed).is_file() {
        return Err(format!("Image path does not exist: {trimmed}"));
    }

    let mut guard = job_store()
        .lock()
        .map_err(|_| "Failed to lock job state.".to_string())?;

    if let Some(existing) = guard.as_ref() {
        if !is_terminal(existing.status) {
            return Err("A job is already running. Please wait for it to finish.".to_string());
        }
    }

    let job_id = format!("job-{}", now_millis());

    let run_name = PathBuf::from(&trimmed)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    let initial = JobState {
        job_id: job_id.clone(),
        status: JobStatus::Preprocessing,
        started_at: std::time::Instant::now(),
        message: "Pipeline started...".to_string(),
        error: None,
        n_colors: None,
        palette: Vec::new(),
        current_layer: None,
        winner_history: Vec::new(),
        final_dir: None,
    };

    *guard = Some(initial.clone());
    drop(guard);

    thread::spawn(move || {
        let repo_root = match PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
        {
            Ok(p) => p,
            Err(e) => {
                set_status(
                    &job_id,
                    JobStatus::Failed,
                    "Could not resolve repo root.".to_string(),
                    Some(e.to_string()),
                );
                return;
            }
        };

        let python_path = repo_root.join("mwca_env/bin/python");
        if !python_path.is_file() {
            set_status(
                &job_id,
                JobStatus::Failed,
                "Python interpreter not found.".to_string(),
                Some(format!("Expected at {}", python_path.display())),
            );
            return;
        }

        let log_path = repo_root.join(format!("output_final_{}/run_log.txt", run_name));
        {
            let lp = log_path.clone();
            let lj = job_id.clone();
            thread::spawn(move || crate::log_tail::tail_run_log(lp, lj));
        }

        let mut cmd = Command::new(&python_path);
        cmd.arg("-u")
            .arg("pipeline.py")
            .arg("--image")
            .arg(&trimmed);

        if let Some(ref size) = stock_size_in {
            cmd.arg("--stock-size-in").arg(size);
        }

        let mut child = match cmd
            .current_dir(&repo_root)
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                set_status(
                    &job_id,
                    JobStatus::Failed,
                    "Failed to start pipeline process.".to_string(),
                    Some(e.to_string()),
                );
                return;
            }
        };

        if let Some(stdout) = child.stdout.take() {
            for line in std::io::BufReader::new(stdout).lines().flatten() {
                let l = line.trim().to_string();

                if l.contains("--- Preprocessor ---") {
                    set_status(
                        &job_id,
                        JobStatus::Preprocessing,
                        "Preprocessing image...".to_string(),
                        None,
                    );
                } else if l.contains("--- Generator ---") {
                    set_status(
                        &job_id,
                        JobStatus::Generating,
                        "Generator building layers...".to_string(),
                        None,
                    );
                    try_load_palette(&repo_root, &job_id);
                } else if l.contains("--- Postprocessor ---") {
                    set_status(
                        &job_id,
                        JobStatus::Postprocessing,
                        "Postprocessor finalizing layers...".to_string(),
                        None,
                    );
                } else if l.starts_with("Final fabrication package saved to") {
                    let raw_dir = l
                        .trim_start_matches("Final fabrication package saved to '")
                        .trim_end_matches("'.")
                        .trim_end_matches('\'')
                        .to_string();

                    let abs_dir = repo_root.join(raw_dir);
                    set_final_dir(&job_id, abs_dir.to_string_lossy().to_string());
                } else if !l.is_empty() {
                    set_message(&job_id, l);
                }
            }
        }

        match child.wait() {
            Ok(exit) if exit.success() => {
                set_status(
                    &job_id,
                    JobStatus::Complete,
                    "Pipeline finished successfully.".to_string(),
                    None,
                );
            }
            Ok(_) => {
                set_status(
                    &job_id,
                    JobStatus::Failed,
                    "Pipeline exited with an error. Check the dev terminal for details."
                        .to_string(),
                    None,
                );
            }
            Err(e) => {
                set_status(
                    &job_id,
                    JobStatus::Failed,
                    "Pipeline process lost.".to_string(),
                    Some(e.to_string()),
                );
            }
        }
    });

    Ok(crate::state::snapshot_from_state(&initial))
}

#[tauri::command]
pub fn get_job_status() -> Result<crate::types::JobSnapshot, String> {
    let guard = job_store()
        .lock()
        .map_err(|_| "Failed to lock job state.".to_string())?;

    if let Some(state) = guard.as_ref() {
        Ok(crate::state::snapshot_from_state(state))
    } else {
        Ok(crate::types::JobSnapshot {
            job_id: "none".to_string(),
            status: JobStatus::Idle,
            elapsed_sec: 0,
            message: "No job has been started yet.".to_string(),
            error: None,
            n_colors: None,
            palette: Vec::new(),
            current_layer: None,
            winner_history: Vec::new(),
            final_dir: None,
        })
    }
}