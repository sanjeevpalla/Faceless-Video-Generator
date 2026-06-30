// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

/// Open a path in the OS file explorer
#[tauri::command]
fn open_in_explorer(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// Get the application data directory
#[tauri::command]
fn get_app_data_dir(app_handle: tauri::AppHandle) -> Result<String, String> {
    let path = app_handle
        .path_resolver()
        .app_data_dir()
        .ok_or("Could not resolve app data directory")?;
    Ok(path.to_string_lossy().to_string())
}

/// Check if a path exists
#[tauri::command]
fn path_exists(path: String) -> bool {
    std::path::Path::new(&path).exists()
}

/// Get file size in bytes
#[tauri::command]
fn get_file_size(path: String) -> Result<u64, String> {
    std::fs::metadata(&path)
        .map(|m| m.len())
        .map_err(|e| e.to_string())
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // Get the main window and configure it
            let window = app.get_window("main").unwrap();

            // Center the window on startup
            window.center().unwrap_or_default();

            // Log the app data directory on startup
            if let Some(app_data) = app.path_resolver().app_data_dir() {
                println!("[Tauri] App data dir: {}", app_data.display());
            }

            println!("[Tauri] Faceless Video Generator started");
            println!("[Tauri] Frontend: http://localhost:1420");
            println!("[Tauri] Backend API: http://localhost:8000");

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            open_in_explorer,
            get_app_data_dir,
            path_exists,
            get_file_size,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
