use serde::Serialize;
use std::time::Instant;

#[derive(Debug, Clone, Copy, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum JobStatus {
    Idle,
    Preprocessing,
    Generating,
    Postprocessing,
    Complete,
    Failed,
}

#[derive(Debug, Clone, Serialize)]
pub struct PaletteColor {
    pub id: u32,
    pub rgb: [u8; 3],
}

#[derive(Debug, Clone, Serialize)]
pub struct LayerWinner {
    pub layer: u32,
    pub color_id: u32,
    pub patches: u64,
}

#[derive(Debug, Clone)]
pub struct JobState {
    pub job_id: String,
    pub status: JobStatus,
    pub started_at: Instant,
    pub message: String,
    pub error: Option<String>,
    pub n_colors: Option<u32>,
    pub palette: Vec<PaletteColor>,
    pub current_layer: Option<u32>,
    pub winner_history: Vec<LayerWinner>,
    pub final_dir: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct JobSnapshot {
    pub job_id: String,
    pub status: JobStatus,
    pub elapsed_sec: u64,
    pub message: String,
    pub error: Option<String>,
    pub n_colors: Option<u32>,
    pub palette: Vec<PaletteColor>,
    pub current_layer: Option<u32>,
    pub winner_history: Vec<LayerWinner>,
    pub final_dir: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FinalArtifact {
    pub name: String,
    pub abs_path: String,
    pub ext: String,
    pub previewable: bool,
    pub category: String,
}