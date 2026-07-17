use std::fs;
use std::fs::File;
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;

use chrono::Local;

use crate::library_store::resolve_library_root;
use crate::library_types::{
    OutputPaths, ParameterSnapshot, PromptRef, RunSource, RunStatus as SavedRunStatus,
    SavedRunSummary,
};
use crate::log_tail::try_load_palette;
use crate::state::{is_terminal, job_store, now_millis, set_final_dir, set_message, set_status};
use crate::types::{JobState, JobStatus};

struct PreparedRun {
    run_root: PathBuf,
    run_json_path: PathBuf,
    runtime_log_abs: PathBuf,
    summary: SavedRunSummary,
}

fn now_rfc3339() -> String {
    Local::now().to_rfc3339()
}

fn run_day_token() -> String {
    Local::now().format("%Y%m%d").to_string()
}

fn write_run_json(path: &Path, summary: &SavedRunSummary) -> Result<(), String> {
    let json = serde_json::to_string_pretty(summary)
        .map_err(|e| format!("Failed to serialize run.json at {}: {e}", path.display()))?;
    fs::write(path, format!("{json}\n"))
        .map_err(|e| format!("Failed to write run.json at {}: {e}", path.display()))
}

fn normalize_prompt(prompt: Option<String>) -> Option<String> {
    prompt.and_then(|p| {
        let trimmed = p.trim().to_string();
        if trimmed.is_empty() {
            None
        } else {
            Some(trimmed)
        }
    })
}

fn allocate_next_run_dir(runs_dir: &Path) -> Result<(String, PathBuf), String> {
    let day = run_day_token();
    let prefix = format!("run-{day}-");
    let mut max_seq = 0_u32;

    if runs_dir.exists() {
        let entries = fs::read_dir(runs_dir)
            .map_err(|e| format!("Failed to read runs directory {}: {e}", runs_dir.display()))?;

        for entry in entries {
            let entry = entry.map_err(|e| format!("Failed to read runs entry: {e}"))?;
            let path = entry.path();
            if !path.is_dir() {
                continue;
            }

            let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
                continue;
            };

            if !name.starts_with(&prefix) {
                continue;
            }

            let seq_part = &name[prefix.len()..];
            if let Ok(seq) = seq_part.parse::<u32>() {
                if seq > max_seq {
                    max_seq = seq;
                }
            }
        }
    }

    let mut next = max_seq + 1;
    while next <= 999 {
        let run_id = format!("{prefix}{next:03}");
        let run_dir = runs_dir.join(&run_id);
        if !run_dir.exists() {
            fs::create_dir(&run_dir)
                .map_err(|e| format!("Failed to create run dir {}: {e}", run_dir.display()))?;
            return Ok((run_id, run_dir));
        }
        next += 1;
    }

    Err(format!(
        "Could not allocate a unique run id for date {} in {}",
        day,
        runs_dir.display()
    ))
}

fn prepare_run_folder(
    project_id: &str,
    image_path: &str,
    prompt: Option<String>,
    parameters: ParameterSnapshot,
) -> Result<PreparedRun, String> {
    let library_root = resolve_library_root()?;
    let project_dir = library_root.join("projects").join(project_id);

    if !project_dir.is_dir() {
        return Err(format!(
            "Selected project does not exist: {}",
            project_dir.display()
        ));
    }

    if !project_dir.join("project.json").is_file() {
        return Err(format!(
            "Selected project is missing project.json: {}",
            project_dir.display()
        ));
    }

    let runs_dir = project_dir.join("runs");
    fs::create_dir_all(&runs_dir)
        .map_err(|e| format!("Failed to ensure runs directory {}: {e}", runs_dir.display()))?;

    let (run_id, run_dir) = allocate_next_run_dir(&runs_dir)?;

    let source_dir = run_dir.join("source");
    let outputs_dir = run_dir.join("outputs");
    let logs_dir = run_dir.join("logs");

    fs::create_dir_all(&source_dir)
        .map_err(|e| format!("Failed to create source directory {}: {e}", source_dir.display()))?;
    fs::create_dir_all(&outputs_dir).map_err(|e| {
        format!(
            "Failed to create outputs directory {}: {e}",
            outputs_dir.display()
        )
    })?;
    fs::create_dir_all(&logs_dir)
        .map_err(|e| format!("Failed to create logs directory {}: {e}", logs_dir.display()))?;

    let source_path = PathBuf::from(image_path);
    let original_filename = source_path
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or_else(|| format!("Image path has no valid filename: {image_path}"))?
        .to_string();

    let input_rel = match source_path.extension().and_then(|s| s.to_str()) {
        Some(ext) if !ext.is_empty() => format!("source/input.{ext}"),
        _ => "source/input".to_string(),
    };
    let input_abs = run_dir.join(&input_rel);

    fs::copy(&source_path, &input_abs).map_err(|e| {
        format!(
            "Failed to copy source image into run folder {} -> {}: {e}",
            source_path.display(),
            input_abs.display()
        )
    })?;

    let prompt_ref = match normalize_prompt(prompt) {
        Some(text) => {
            let prompt_rel = "source/prompt.md".to_string();
            let prompt_abs = run_dir.join(&prompt_rel);
            fs::write(&prompt_abs, format!("{text}\n"))
                .map_err(|e| format!("Failed to write prompt file {}: {e}", prompt_abs.display()))?;
            Some(PromptRef { path: prompt_rel })
        }
        None => None,
    };

    let runtime_log_rel = "logs/runtime.log".to_string();
    let runtime_log_abs = run_dir.join(&runtime_log_rel);

    let mut runtime_log = File::create(&runtime_log_abs)
        .map_err(|e| format!("Failed to create runtime log {}: {e}", runtime_log_abs.display()))?;
    writeln!(
        runtime_log,
        "Run {} created at {} for project {}",
        run_id,
        now_rfc3339(),
        project_id
    )
    .map_err(|e| format!("Failed to initialize runtime log {}: {e}", runtime_log_abs.display()))?;

    let summary = SavedRunSummary {
        schema_version: 1,
        run_id: run_id.clone(),
        project_id: project_id.to_string(),
        status: SavedRunStatus::Pending,
        created_at: now_rfc3339(),
        started_at: None,
        finished_at: None,
        source: RunSource {
            original_filename,
            input_path: input_rel,
        },
        prompt: prompt_ref,
        parameters,
        outputs: OutputPaths {
            generator: "outputs/generator".to_string(),
            postprocessed: "outputs/postprocessed".to_string(),
            final_output: "outputs/final".to_string(),
        },
        runtime_log_path: runtime_log_rel,
        exit_code: None,
    };

    let run_json_path = run_dir.join("run.json");
    write_run_json(&run_json_path, &summary)?;

    Ok(PreparedRun {
        run_root: run_dir,
        run_json_path,
        runtime_log_abs,
        summary,
    })
}

fn append_runtime_log(path: &Path, line: &str) {
    if let Ok(mut file) = fs::OpenOptions::new().append(true).create(true).open(path) {
        let _ = writeln!(file, "{line}");
    }
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<bool, String> {
    if !src.exists() {
        return Ok(false);
    }
    if !src.is_dir() {
        return Err(format!("Source path is not a directory: {}", src.display()));
    }

    fs::create_dir_all(dst)
        .map_err(|e| format!("Failed to create destination directory {}: {e}", dst.display()))?;

    let entries = fs::read_dir(src)
        .map_err(|e| format!("Failed to read source directory {}: {e}", src.display()))?;

    for entry in entries {
        let entry = entry.map_err(|e| format!("Failed to read directory entry: {e}"))?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());

        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else if src_path.is_file() {
            fs::copy(&src_path, &dst_path).map_err(|e| {
                format!(
                    "Failed to copy file {} -> {}: {e}",
                    src_path.display(),
                    dst_path.display()
                )
            })?;
        }
    }

    Ok(true)
}

fn copy_pipeline_outputs(
    repo_root: &Path,
    run_name: &str,
    final_src_from_stdout: Option<&PathBuf>,
    run_root: &Path,
    require_final_on_success: bool,
) -> Result<(), String> {
    let generator_src = repo_root.join(format!("output_generator_{run_name}"));
    let postprocessed_src = repo_root.join(format!("output_postprocessed_{run_name}"));
    let final_src = final_src_from_stdout
        .cloned()
        .unwrap_or_else(|| repo_root.join(format!("output_final_{run_name}")));

    let outputs_root = run_root.join("outputs");
    let generator_dst = outputs_root.join("generator");
    let postprocessed_dst = outputs_root.join("postprocessed");
    let final_dst = outputs_root.join("final");

    let _copied_generator = copy_dir_recursive(&generator_src, &generator_dst)?;
    let _copied_post = copy_dir_recursive(&postprocessed_src, &postprocessed_dst)?;
    let copied_final = copy_dir_recursive(&final_src, &final_dst)?;

    if require_final_on_success && !copied_final {
        return Err(format!(
            "Expected final output directory was not found for successful run: {}",
            final_src.display()
        ));
    }

    Ok(())
}

#[tauri::command]
pub fn start_job(
    project_id: String,
    image_path: String,
    prompt: Option<String>,
    stock_size_in: Option<String>,
    bridge_count_in: Option<u32>,
    merge_visible_fraction: Option<f64>,
    omega_budget_factor: Option<f64>,
) -> Result<crate::types::JobSnapshot, String> {
    let project_id_trimmed = project_id.trim().to_string();
    if project_id_trimmed.is_empty() {
        return Err("Please select a project first.".to_string());
    }

    let image_path_trimmed = image_path.trim().to_string();
    if image_path_trimmed.is_empty() {
        return Err("Please choose an image path first.".to_string());
    }
    if !PathBuf::from(&image_path_trimmed).is_file() {
        return Err(format!("Image path does not exist: {image_path_trimmed}"));
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

    let parameter_snapshot = ParameterSnapshot {
        stock_size_in: stock_size_in.clone(),
        support_bridges_per_patch: bridge_count_in.unwrap_or(5),
        merge_visible_fraction,
        omega_budget_factor,
        generate_composite_preview: true,
        generate_showcase_preview: true,
    };

    let prepared = prepare_run_folder(
        &project_id_trimmed,
        &image_path_trimmed,
        prompt,
        parameter_snapshot,
    )?;

    let run_name = PathBuf::from(&image_path_trimmed)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    let initial = JobState {
        job_id: job_id.clone(),
        status: JobStatus::Preprocessing,
        started_at: std::time::Instant::now(),
        message: format!("Run {} prepared. Starting pipeline...", prepared.summary.run_id),
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

        let mut run_summary = prepared.summary.clone();
        run_summary.status = SavedRunStatus::Running;
        run_summary.started_at = Some(now_rfc3339());
        if let Err(e) = write_run_json(&prepared.run_json_path, &run_summary) {
            set_status(
                &job_id,
                JobStatus::Failed,
                "Failed to update run status to running.".to_string(),
                Some(e),
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
            .arg(&image_path_trimmed);

        if let Some(ref size) = stock_size_in {
            cmd.arg("--stock-size-in").arg(size);
        }

        if let Some(bc) = bridge_count_in {
            cmd.arg("--bridge-count").arg(bc.to_string());
        }

        if let Some(v) = merge_visible_fraction {
            cmd.arg("--merge-visible-fraction").arg(v.to_string());
        }

        if let Some(v) = omega_budget_factor {
            cmd.arg("--omega-budget-factor").arg(v.to_string());
        }

let mut child = match cmd
            .current_dir(&repo_root)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                run_summary.status = SavedRunStatus::Failed;
                run_summary.finished_at = Some(now_rfc3339());
                run_summary.exit_code = Some(-1);
                let _ = write_run_json(&prepared.run_json_path, &run_summary);

                set_status(
                    &job_id,
                    JobStatus::Failed,
                    "Failed to start pipeline process.".to_string(),
                    Some(e.to_string()),
                );
                return;
            }
        };

        // Capture stderr into runtime.log without using it for status parsing.
        let stderr_handle = child.stderr.take().map(|stderr| {
            let runtime_log_path = prepared.runtime_log_abs.clone();
            thread::spawn(move || {
                for line in std::io::BufReader::new(stderr).lines().flatten() {
                    append_runtime_log(&runtime_log_path, &format!("[stderr] {line}"));
                }
            })
        });

        let mut final_src_from_stdout: Option<PathBuf> = None;

        // Parse stdout for status transitions and final output location, and also log it.
        if let Some(stdout) = child.stdout.take() {
            for line in std::io::BufReader::new(stdout).lines().flatten() {
                let l = line.trim().to_string();
                append_runtime_log(&prepared.runtime_log_abs, &format!("[stdout] {l}"));

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
                    final_src_from_stdout = Some(abs_dir.clone());
                    set_final_dir(&job_id, abs_dir.to_string_lossy().to_string());
                } else if !l.is_empty() {
                    set_message(&job_id, l);
                }
            }
        }

        let wait_result = child.wait();

        if let Some(handle) = stderr_handle {
            let _ = handle.join();
        }

        let (process_success, process_exit_code, process_message, process_error) = match wait_result {
            Ok(exit) if exit.success() => (
                true,
                exit.code().unwrap_or(0),
                "Pipeline finished successfully.".to_string(),
                None,
            ),
            Ok(exit) => (
                false,
                exit.code().unwrap_or(1),
                "Pipeline exited with an error. Check logs/runtime.log for details.".to_string(),
                None,
            ),
            Err(e) => (
                false,
                -1,
                "Pipeline process lost.".to_string(),
                Some(e.to_string()),
            ),
        };

        // Always attempt output copy after process finishes.
        let copy_error = copy_pipeline_outputs(
            &repo_root,
            &run_name,
            final_src_from_stdout.as_ref(),
            &prepared.run_root,
            process_success,
        )
        .err();

        if let Some(err) = &copy_error {
            append_runtime_log(
                &prepared.runtime_log_abs,
                &format!("[system] Output copy error: {err}"),
            );
        }

        let final_success = process_success && copy_error.is_none();

        run_summary.status = if final_success {
            SavedRunStatus::Completed
        } else {
            SavedRunStatus::Failed
        };
        run_summary.finished_at = Some(now_rfc3339());
        run_summary.exit_code = Some(process_exit_code);
        let _ = write_run_json(&prepared.run_json_path, &run_summary);

        let final_message = match &copy_error {
            Some(err) => format!("{process_message} Output copy failed: {err}"),
            None => process_message,
        };

        let final_error = if process_error.is_some() {
            process_error
        } else {
            copy_error
        };

        set_status(
            &job_id,
            if final_success {
                JobStatus::Complete
            } else {
                JobStatus::Failed
            },
            final_message,
            final_error,
        );
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