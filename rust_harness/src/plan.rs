//! Timing plan: one row per (kernel, opt level) module with the reps used per timed call.

use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
pub struct Cell {
    pub key: String,
    pub group: String,
    pub opt_level: String,
    pub path: PathBuf,
    pub reps: u32,
}

pub fn load(path: &Path) -> Result<Vec<Cell>, String> {
    let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut cells = Vec::new();
    for (index, line) in text.lines().enumerate().skip(1) {
        let fields: Vec<&str> = line.split(',').collect();
        if fields.len() != 5 {
            return Err(format!("{}:{}: expected 5 fields", path.display(), index + 1));
        }
        let reps: u32 = fields[4].parse().map_err(|e| format!("reps on line {}: {e}", index + 1))?;
        cells.push(Cell {
            key: fields[0].to_string(),
            group: fields[1].to_string(),
            opt_level: fields[2].to_string(),
            path: PathBuf::from(fields[3]),
            reps,
        });
    }
    if cells.is_empty() {
        return Err(format!("{} contains no cells", path.display()));
    }
    Ok(cells)
}
