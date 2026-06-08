use serde::{Deserialize, Serialize};
use std::fs;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

// ─── Job status enum ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum JobStatus {
    Idle,
    Preprocessing,
    Generating,
    Postprocessing,
    Complete,
    Failed,
}

// ─── Rich data types (sent to frontend) ──────────────────────────────────────

// One detected color from the preprocessor palette.
#[derive(Debug, Clone, Serialize)]
struct PaletteColor {
    id: u32,
    rgb: [u8; 3],
}

// The winning color chosen for one generator layer.
#[derive(Debug, Clone, Serialize)]
struct LayerWinner {
    layer: u32,
    color_id: u32,
    patches: u64,
}

// ─── Internal job state (not serialized directly) ─────────────────────────────

#[derive(Debug, Clone)]
struct JobState {
    job_id: String,
    status: JobStatus,
    started_at: Instant,
    message: String,
    error: Option<String>,
    // Preprocessor results
    n_colors: Option<u32>,
    palette: Vec<PaletteColor>,
    // Generator results
    current_layer: Option<u32>,
    winner_history: Vec<LayerWinner>,
    // Postprocessor results
    final_dir: Option<String>,
}

// ─── Serializable snapshot sent to frontend ───────────────────────────────────

#[derive(Debug, Clone, Serialize)]
struct JobSnapshot {
    job_id: String,
    status: JobStatus,
    elapsed_sec: u64,
    message: String,
    error: Option<String>,
    n_colors: Option<u32>,
    palette: Vec<PaletteColor>,
    current_layer: Option<u32>,
    winner_history: Vec<LayerWinner>,
    final_dir: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct FinalArtifact {
    name: String,
    abs_path: String,
    ext: String,
    previewable: bool,
    category: String,
}

fn artifact_category(ext: &str) -> (&'static str, bool) {
    match ext {
        "png" => ("image", true),
        "dxf" => ("vector", false),
        "md" => ("doc", false),
        "json" => ("data", false),
        "txt" => ("text", false),
        _ => ("other", false),
    }
}

// ─── Global single-job store ──────────────────────────────────────────────────

static JOB_STATE: OnceLock<Mutex<Option<JobState>>> = OnceLock::new();

fn job_store() -> &'static Mutex<Option<JobState>> {
    JOB_STATE.get_or_init(|| Mutex::new(None))
}

fn is_terminal(status: JobStatus) -> bool {
    matches!(status, JobStatus::Complete | JobStatus::Failed)
}

fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

fn snapshot_from_state(state: &JobState) -> JobSnapshot {
    JobSnapshot {
        job_id: state.job_id.clone(),
        status: state.status,
        elapsed_sec: state.started_at.elapsed().as_secs(),
        message: state.message.clone(),
        error: state.error.clone(),
        n_colors: state.n_colors,
        palette: state.palette.clone(),
        current_layer: state.current_layer,
        winner_history: state.winner_history.clone(),
        final_dir: state.final_dir.clone(),
    }
}

// ─── Focused state-update helpers (each mutates only one field) ───────────────

fn set_status(job_id: &str, status: JobStatus, message: String, error: Option<String>) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.status = status;
                s.message = message;
                s.error = error;
            }
        }
    }
}

fn set_message(job_id: &str, message: String) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.message = message;
            }
        }
    }
}

fn set_n_colors(job_id: &str, n: u32) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.n_colors = Some(n);
            }
        }
    }
}

fn set_current_layer(job_id: &str, layer: u32) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.current_layer = Some(layer);
                // Only update the visible message while still in the generating stage.
                // If we are already postprocessing or later, a stale log-tail read
                // should not overwrite the more current status message.
                if s.status == JobStatus::Generating {
                    s.message = format!("Generator: calculating layer {}...", layer);
                }
            }
        }
    }
}

fn push_winner(job_id: &str, winner: LayerWinner) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.winner_history.push(winner);
            }
        }
    }
}

fn set_palette(job_id: &str, palette: Vec<PaletteColor>) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.palette = palette;
            }
        }
    }
}

fn set_final_dir(job_id: &str, dir: String) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.final_dir = Some(dir);
            }
        }
    }
}

// Returns true if the job is done (or unknown). Used to stop background threads.
fn job_is_terminal(job_id: &str) -> bool {
    if let Ok(g) = job_store().lock() {
        if let Some(s) = g.as_ref() {
            if s.job_id == job_id {
                return is_terminal(s.status);
            }
        }
    }
    true
}

// ─── Line parsers for run_log.txt ─────────────────────────────────────────────

// Matches: "  >>> Auto-selected n_colors = 5"
fn try_parse_n_colors(line: &str, job_id: &str) {
    if let Some(rest) = line.trim().strip_prefix(">>> Auto-selected n_colors = ") {
        if let Ok(n) = rest.trim().parse::<u32>() {
            set_n_colors(job_id, n);
        }
    }
}

// Matches: "--- Calculating Layer 0 ---"
fn try_parse_layer(line: &str, job_id: &str) {
    let trimmed = line.trim();
    if let Some(rest) = trimmed.strip_prefix("--- Calculating Layer ") {
        let digits: String = rest.chars().take_while(|c| c.is_ascii_digit()).collect();
        if let Ok(n) = digits.parse::<u32>() {
            set_current_layer(job_id, n);
        }
    }
}

// Matches: "WINNER: Layer 0 → Color 4 (988739 patches connected)"
// Note: → is Unicode U+2192
fn try_parse_winner(line: &str, job_id: &str) {
    let trimmed = line.trim();
    if !trimmed.starts_with("WINNER: Layer ") {
        return;
    }
    let rest = &trimmed["WINNER: Layer ".len()..];

    // Split on " → " (with unicode arrow)
    let arrow = " \u{2192} ";
    let mut parts = rest.splitn(2, arrow);
    let layer_str = match parts.next() { Some(s) => s, None => return };
    let color_part = match parts.next() { Some(s) => s, None => return };

    let layer: u32 = match layer_str.trim().parse() {
        Ok(n) => n,
        Err(_) => return,
    };

    // color_part = "Color 4 (988739 patches connected)"
    let color_rest = color_part.strip_prefix("Color ").unwrap_or(color_part);
    let mut color_iter = color_rest.splitn(2, " (");
    let color_id_str = match color_iter.next() { Some(s) => s, None => return };
    let patches_part = color_iter.next().unwrap_or("");

    let color_id: u32 = match color_id_str.trim().parse() {
        Ok(n) => n,
        Err(_) => return,
    };
    let patches: u64 = {
        let digits: String = patches_part.chars().take_while(|c| c.is_ascii_digit()).collect();
        digits.parse().unwrap_or(0)
    };

    push_winner(job_id, LayerWinner { layer, color_id, patches });
}

// Reads preprocessor_output/run_metadata.json and loads the palette.
// Called once when pipeline.py stdout shows "--- Generator ---" (preprocessor is done).
fn try_load_palette(repo_root: &PathBuf, job_id: &str) {
    let path = repo_root.join("preprocessor_output/run_metadata.json");
    if !path.is_file() {
        return;
    }
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return,
    };

    // These structs are only used here for JSON parsing so they stay local.
    #[derive(Deserialize)]
    struct RawMeta { palette: Vec<RawColor> }
    #[derive(Deserialize)]
    struct RawColor { id: u32, rgb: Vec<u8> }

    let meta: RawMeta = match serde_json::from_str(&content) {
        Ok(m) => m,
        Err(_) => return,
    };

    let palette: Vec<PaletteColor> = meta.palette.into_iter().map(|c| PaletteColor {
        id: c.id,
        rgb: [
            c.rgb.first().copied().unwrap_or(0),
            c.rgb.get(1).copied().unwrap_or(0),
            c.rgb.get(2).copied().unwrap_or(0),
        ],
    }).collect();

    set_palette(job_id, palette);
}

// ─── Log-tail background thread ───────────────────────────────────────────────
//
// Waits for run_log.txt to appear, then reads it line-by-line as the pipeline
// writes it. Parses n_colors, per-layer progress, and winner selections.

fn tail_run_log(run_log_path: PathBuf, job_id: String) {
    // Wait up to 60 seconds for the file to exist (pipeline creates it early).
    let timeout = Duration::from_secs(60);
    let mut waited = Duration::ZERO;

    while !run_log_path.exists() {
        if waited >= timeout || job_is_terminal(&job_id) {
            return;
        }
        thread::sleep(Duration::from_millis(500));
        waited += Duration::from_millis(500);
    }

    let file = match File::open(&run_log_path) {
        Ok(f) => f,
        Err(_) => return,
    };

    let mut reader = BufReader::new(file);
    let mut line = String::new();

    loop {
        line.clear();
        match reader.read_line(&mut line) {
            // 0 bytes = no new content yet; wait briefly and retry.
            Ok(0) => {
                if job_is_terminal(&job_id) {
                    break;
                }
                thread::sleep(Duration::from_millis(250));
            }
            Ok(_) => {
                let l = line.trim();
                try_parse_n_colors(l, &job_id);
                try_parse_layer(l, &job_id);
                if l.starts_with("WINNER:") {
                    try_parse_winner(l, &job_id);
                }
            }
            Err(_) => break,
        }
    }
}

// ─── Tauri commands ───────────────────────────────────────────────────────────

#[tauri::command]
fn start_job(image_path: String) -> Result<JobSnapshot, String> {
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

    // Derive run_name the same way pipeline.py does (image filename without extension).
    let run_name = PathBuf::from(&trimmed)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();

    let initial = JobState {
        job_id: job_id.clone(),
        status: JobStatus::Preprocessing,
        started_at: Instant::now(),
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
                set_status(&job_id, JobStatus::Failed,
                    "Could not resolve repo root.".to_string(), Some(e.to_string()));
                return;
            }
        };

        let python_path = repo_root.join("mwca_env/bin/python");
        if !python_path.is_file() {
            set_status(&job_id, JobStatus::Failed,
                "Python interpreter not found.".to_string(),
                Some(format!("Expected at {}", python_path.display())));
            return;
        }

        // Start the log-tail thread before launching the process so it catches
        // early writes (preprocessor output appears quickly).
        let log_path = repo_root.join(format!("output_final_{}/run_log.txt", run_name));
        {
            let lp = log_path.clone();
            let lj = job_id.clone();
            thread::spawn(move || tail_run_log(lp, lj));
        }

        // Launch pipeline.py with stdout piped so we can read it line-by-line.
        // stderr is inherited so errors still appear in the dev terminal.
        let mut child = match Command::new(&python_path)
            .arg("-u")
            .arg("pipeline.py")
            .arg("--image")
            .arg(&trimmed)
            .current_dir(&repo_root)
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                set_status(&job_id, JobStatus::Failed,
                    "Failed to start pipeline process.".to_string(), Some(e.to_string()));
                return;
            }
        };

        // ── Parse pipeline.py stdout for stage transitions ──
        // pipeline.py prints "\n--- Preprocessor ---", "\n--- Generator ---", etc.
        // via run_step(). These are the authoritative stage boundary markers.
        if let Some(stdout) = child.stdout.take() {
            for line in BufReader::new(stdout).lines().flatten() {
                let l = line.trim().to_string();

                if l.contains("--- Preprocessor ---") {
                    set_status(&job_id, JobStatus::Preprocessing,
                        "Preprocessing image...".to_string(), None);

                } else if l.contains("--- Generator ---") {
                    set_status(&job_id, JobStatus::Generating,
                        "Generator building layers...".to_string(), None);
                    // Preprocessor just finished — safe to read palette now.
                    try_load_palette(&repo_root, &job_id);

                } else if l.contains("--- Postprocessor ---") {
                    set_status(&job_id, JobStatus::Postprocessing,
                        "Postprocessor finalizing layers...".to_string(), None);

                } else if l.starts_with("Final fabrication package saved to") {
                    // Capture the output directory shown in the success message.
                    let raw_dir = l
                        .trim_start_matches("Final fabrication package saved to '")
                        .trim_end_matches("'.")
                        .trim_end_matches('\'')
                        .to_string();

                    let abs_dir = repo_root.join(raw_dir);
                    set_final_dir(&job_id, abs_dir.to_string_lossy().to_string());

                } else if !l.is_empty() {
                    // Show any other pipeline output as the live status message.
                    set_message(&job_id, l);
                }
            }
        }

        // ── Set final terminal status from process exit code ──
        match child.wait() {
            Ok(exit) if exit.success() => {
                set_status(&job_id, JobStatus::Complete,
                    "Pipeline finished successfully.".to_string(), None);
            }
            Ok(_) => {
                set_status(&job_id, JobStatus::Failed,
                    "Pipeline exited with an error. Check the dev terminal for details.".to_string(),
                    None);
            }
            Err(e) => {
                set_status(&job_id, JobStatus::Failed,
                    "Pipeline process lost.".to_string(), Some(e.to_string()));
            }
        }
    });

    Ok(snapshot_from_state(&initial))
}

#[tauri::command]
fn get_job_status() -> Result<JobSnapshot, String> {
    let guard = job_store()
        .lock()
        .map_err(|_| "Failed to lock job state.".to_string())?;

    if let Some(state) = guard.as_ref() {
        Ok(snapshot_from_state(state))
    } else {
        Ok(JobSnapshot {
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

#[tauri::command]
fn list_final_artifacts(final_dir: String) -> Result<Vec<FinalArtifact>, String> {
    let dir = PathBuf::from(final_dir.trim());

    if !dir.exists() {
        return Err(format!("Final directory does not exist: {}", dir.display()));
    }
    if !dir.is_dir() {
        return Err(format!("Path is not a directory: {}", dir.display()));
    }

    let mut out: Vec<FinalArtifact> = Vec::new();

    let entries = fs::read_dir(&dir)
        .map_err(|e| format!("Failed to read final directory: {e}"))?;

    for entry in entries {
        let entry = entry.map_err(|e| format!("Bad directory entry: {e}"))?;
        let path = entry.path();
        if !path.is_file() {
            continue;
        }

        let ext = path
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();

        if !matches!(ext.as_str(), "png" | "dxf" | "md" | "json" | "txt") {
            continue;
        }

        let (category, previewable) = artifact_category(&ext);

        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_string();

        let abs_path = path
            .canonicalize()
            .unwrap_or(path.clone())
            .to_string_lossy()
            .to_string();

        out.push(FinalArtifact {
            name,
            abs_path,
            ext,
            previewable,
            category: category.to_string(),
        });
    }

    out.sort_by(|a, b| {
        let a_png_layer = a.ext == "png" && a.name.starts_with("Layer_");
        let b_png_layer = b.ext == "png" && b.name.starts_with("Layer_");

        match (a_png_layer, b_png_layer) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        }
    });

    Ok(out)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![start_job, get_job_status, list_final_artifacts])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}