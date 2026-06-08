use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};
use crate::types::{JobState, JobStatus, JobSnapshot, PaletteColor, LayerWinner};

static JOB_STATE: OnceLock<Mutex<Option<JobState>>> = OnceLock::new();

pub fn job_store() -> &'static Mutex<Option<JobState>> {
    JOB_STATE.get_or_init(|| Mutex::new(None))
}

pub fn is_terminal(status: JobStatus) -> bool {
    matches!(status, JobStatus::Complete | JobStatus::Failed)
}

pub fn now_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

pub fn snapshot_from_state(state: &JobState) -> JobSnapshot {
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

pub fn set_status(job_id: &str, status: JobStatus, message: String, error: Option<String>) {
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

pub fn set_message(job_id: &str, message: String) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.message = message;
            }
        }
    }
}

pub fn set_n_colors(job_id: &str, n: u32) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.n_colors = Some(n);
            }
        }
    }
}

pub fn set_current_layer(job_id: &str, layer: u32) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.current_layer = Some(layer);
                if s.status == JobStatus::Generating {
                    s.message = format!("Generator: calculating layer {}...", layer);
                }
            }
        }
    }
}

pub fn push_winner(job_id: &str, winner: LayerWinner) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.winner_history.push(winner);
            }
        }
    }
}

pub fn set_palette(job_id: &str, palette: Vec<PaletteColor>) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.palette = palette;
            }
        }
    }
}

pub fn set_final_dir(job_id: &str, dir: String) {
    if let Ok(mut g) = job_store().lock() {
        if let Some(s) = g.as_mut() {
            if s.job_id == job_id {
                s.final_dir = Some(dir);
            }
        }
    }
}

pub fn job_is_terminal(job_id: &str) -> bool {
    if let Ok(g) = job_store().lock() {
        if let Some(s) = g.as_ref() {
            if s.job_id == job_id {
                return is_terminal(s.status);
            }
        }
    }
    true
}