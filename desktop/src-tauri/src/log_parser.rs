use crate::state::{set_n_colors, set_current_layer, push_winner};
use crate::types::LayerWinner;

pub fn try_parse_n_colors(line: &str, job_id: &str) {
    if let Some(rest) = line.trim().strip_prefix(">>> Auto-selected n_colors = ") {
        if let Ok(n) = rest.trim().parse::<u32>() {
            set_n_colors(job_id, n);
        }
    }
}

pub fn try_parse_layer(line: &str, job_id: &str) {
    let trimmed = line.trim();
    if let Some(rest) = trimmed.strip_prefix("--- Calculating Layer ") {
        let digits: String = rest.chars().take_while(|c| c.is_ascii_digit()).collect();
        if let Ok(n) = digits.parse::<u32>() {
            set_current_layer(job_id, n);
        }
    }
}

pub fn try_parse_winner(line: &str, job_id: &str) {
    let trimmed = line.trim();
    if !trimmed.starts_with("WINNER: Layer ") {
        return;
    }
    let rest = &trimmed["WINNER: Layer ".len()..];

    let arrow = " \u{2192} ";
    let mut parts = rest.splitn(2, arrow);
    let layer_str = match parts.next() {
        Some(s) => s,
        None => return,
    };
    let color_part = match parts.next() {
        Some(s) => s,
        None => return,
    };

    let layer: u32 = match layer_str.trim().parse() {
        Ok(n) => n,
        Err(_) => return,
    };

    let color_rest = color_part.strip_prefix("Color ").unwrap_or(color_part);
    let mut color_iter = color_rest.splitn(2, " (");
    let color_id_str = match color_iter.next() {
        Some(s) => s,
        None => return,
    };
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