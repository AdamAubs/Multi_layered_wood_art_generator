use std::fs::File;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::thread;
use std::time::Duration;
use serde::Deserialize;

use crate::log_parser::{try_parse_n_colors, try_parse_layer, try_parse_winner};
use crate::state::{job_is_terminal, set_palette};
use crate::types::PaletteColor;

pub fn tail_run_log(run_log_path: PathBuf, job_id: String) {
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

pub fn try_load_palette(repo_root: &PathBuf, job_id: &str) {
    let path = repo_root.join("preprocessor_output/run_metadata.json");
    if !path.is_file() {
        return;
    }
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return,
    };

    #[derive(Deserialize)]
    struct RawMeta {
        palette: Vec<RawColor>,
    }
    #[derive(Deserialize)]
    struct RawColor {
        id: u32,
        rgb: Vec<u8>,
    }

    let meta: RawMeta = match serde_json::from_str(&content) {
        Ok(m) => m,
        Err(_) => return,
    };

    let palette: Vec<PaletteColor> = meta
        .palette
        .into_iter()
        .map(|c| PaletteColor {
            id: c.id,
            rgb: [
                c.rgb.first().copied().unwrap_or(0),
                c.rgb.get(1).copied().unwrap_or(0),
                c.rgb.get(2).copied().unwrap_or(0),
            ],
        })
        .collect();

    set_palette(job_id, palette);
}