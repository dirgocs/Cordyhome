// Sem console extra no Windows em produção.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod diag;
mod hub;

use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

/// Argumento usado quando o Windows abre o app na inicialização: só a bandeja, sem janela.
const HIDDEN_ARG: &str = "--hidden";

fn show_main(app: &AppHandle) {
    match app.get_webview_window("main") {
        Some(window) => {
            let _ = window.unminimize();
            let _ = window.show();
            let _ = window.set_focus();
        }
        None => diag::log("Janela principal não encontrada"),
    }
}

/// Liga o "iniciar com o Windows" na primeira execução. Depois disso vale a escolha do menu.
fn configure_autostart_once(app: &AppHandle) {
    let Ok(dir) = app.path().app_local_data_dir() else { return };
    let marker = dir.join("autostart-configurado");
    if marker.exists() {
        return;
    }
    if app.autolaunch().enable().is_ok() {
        let _ = std::fs::create_dir_all(&dir);
        let _ = std::fs::write(marker, b"1");
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Abrir o Cordyhome", true, None::<&str>)?;
    let autostart = CheckMenuItem::with_id(
        app,
        "autostart",
        "Iniciar com o Windows",
        true,
        app.autolaunch().is_enabled().unwrap_or(false),
        None::<&str>,
    )?;
    let version = MenuItem::with_id(
        app,
        "version",
        format!("Versão {}", app.package_info().version),
        false,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(
        app,
        "quit",
        "Sair (para de gravar o consumo)",
        true,
        None::<&str>,
    )?;
    let separator = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&open, &autostart, &version, &separator, &quit])?;

    let autostart_item = autostart.clone();
    TrayIconBuilder::with_id("main")
        .icon(app.default_window_icon().cloned().expect("ícone do app"))
        .tooltip("Cordyhome")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| match event.id().as_ref() {
            "open" => show_main(app),
            "autostart" => {
                let launcher = app.autolaunch();
                let enabled = launcher.is_enabled().unwrap_or(false);
                let _ = if enabled { launcher.disable() } else { launcher.enable() };
                let _ = autostart_item.set_checked(launcher.is_enabled().unwrap_or(false));
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn main() {
    diag::install_panic_hook();
    diag::log(&format!(
        "Abrindo o Cordyhome {} (args: {:?})",
        env!("CARGO_PKG_VERSION"),
        std::env::args().skip(1).collect::<Vec<_>>()
    ));
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec![HIDDEN_ARG]),
        ))
        .manage(hub::HubProcess::default())
        .setup(|app| {
            let handle = app.handle().clone();
            configure_autostart_once(&handle);
            if let Err(e) = build_tray(&handle) {
                // Sem ícone na bandeja o app ainda funciona pela janela.
                diag::log(&format!("Falha ao criar o ícone da bandeja: {e}"));
            }
            if std::env::args().any(|arg| arg == HIDDEN_ARG) {
                diag::log("Iniciado com o Windows: só na bandeja");
            } else {
                show_main(&handle);
            }
            std::thread::spawn(move || hub::run(handle));
            Ok(())
        })
        .on_window_event(|window, event| {
            // Fechar a janela só a esconde: o hub continua gravando o consumo.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("erro ao iniciar o Cordyhome");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            hub::stop(app);
        }
    });
}
