//! Registro do app de desktop em `<dados locais>/com.cordyhome.app/logs/app.log`.
//!
//! No Windows o app não tem console, então um erro na abertura passaria sem rastro. Aqui
//! cada etapa é anotada e um panic vira uma mensagem na tela, além de ir para o arquivo.

use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const IDENTIFIER: &str = "com.cordyhome.app";

/// Mesma pasta que `app_local_data_dir()` do Tauri, disponível antes do app existir.
pub fn log_dir() -> PathBuf {
    #[cfg(windows)]
    let base = std::env::var_os("LOCALAPPDATA").map(PathBuf::from);
    #[cfg(not(windows))]
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".local/share")));
    base.unwrap_or_else(std::env::temp_dir)
        .join(IDENTIFIER)
        .join("logs")
}

pub fn log(message: &str) {
    let dir = log_dir();
    let _ = fs::create_dir_all(&dir);
    if let Ok(mut file) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(dir.join("app.log"))
    {
        let secs = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(file, "[{secs}] {message}");
    }
}

pub fn install_panic_hook() {
    std::panic::set_hook(Box::new(|info| {
        let message = format!("Erro inesperado: {info}");
        log(&message);
        error_box(&format!(
            "O Cordyhome encontrou um erro e vai fechar.\n\n{message}\n\nDetalhes em {}",
            log_dir().join("app.log").display()
        ));
    }));
}

#[cfg(windows)]
pub fn error_box(text: &str) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
    let wide = |s: &str| s.encode_utf16().chain(Some(0)).collect::<Vec<u16>>();
    let (text, title) = (wide(text), wide("Cordyhome"));
    unsafe {
        MessageBoxW(std::ptr::null_mut(), text.as_ptr(), title.as_ptr(), MB_OK | MB_ICONERROR);
    }
}

#[cfg(not(windows))]
pub fn error_box(text: &str) {
    eprintln!("{text}");
}
