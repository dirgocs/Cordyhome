//! Prepara e roda o hub em Python que vem dentro do instalador.
//!
//! Na primeira execução (e depois de cada atualização) o uv embutido cria um venv com o
//! Python 3.12 gerenciado por ele, isolado do Python que o PC já tenha. Depois o hub sobe
//! em segundo plano e a janela troca a tela de carregamento pela interface do hub.

use std::fs::{self, File};
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use command_group::{CommandGroup, GroupChild};
use tauri::{AppHandle, Manager, Url};

pub const PORT: u16 = 8420;

/// O hub respondeu e a interface pode ser aberta.
static READY: AtomicBool = AtomicBool::new(false);
/// A janela não pôde ser criada: a interface abre no navegador padrão.
static USE_BROWSER: AtomicBool = AtomicBool::new(false);

pub fn is_ready() -> bool {
    READY.load(Ordering::SeqCst)
}

pub fn use_browser() {
    USE_BROWSER.store(true, Ordering::SeqCst);
}

pub fn url() -> Url {
    Url::parse(&format!("http://localhost:{PORT}/")).expect("URL válida")
}

#[derive(Default)]
pub struct HubProcess(Mutex<Option<GroupChild>>);

#[cfg(windows)]
const UV_EXE: &str = "uv.exe";
#[cfg(not(windows))]
const UV_EXE: &str = "uv";

#[cfg(windows)]
fn venv_python(venv: &Path) -> PathBuf {
    venv.join("Scripts").join("python.exe")
}
#[cfg(not(windows))]
fn venv_python(venv: &Path) -> PathBuf {
    venv.join("bin").join("python")
}

/// Processos filhos sem janela de console no Windows.
fn hide_console(cmd: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    let _ = cmd;
}

/// Inicia o processo num job object (Windows) ou grupo de processos, para matar o hub e os
/// filhos de uma vez. O command-group sobrescreve os flags do Command, então o
/// CREATE_NO_WINDOW vai pelo builder dele.
fn spawn_group(cmd: &mut Command) -> std::io::Result<GroupChild> {
    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.group().creation_flags(CREATE_NO_WINDOW).spawn()
    }
    #[cfg(not(windows))]
    cmd.group_spawn()
}

pub fn run(app: AppHandle) {
    if let Err(message) = start(&app) {
        crate::diag::log(&format!("Erro ao iniciar o hub: {message}"));
        // Repete por alguns segundos caso a tela de carregamento ainda esteja abrindo.
        for _ in 0..5 {
            status(&app, &message, true);
            std::thread::sleep(Duration::from_secs(1));
        }
    }
}

pub fn stop(app: &AppHandle) {
    if let Some(mut child) = app.state::<HubProcess>().0.lock().unwrap().take() {
        // Mata o grupo inteiro: no Windows o python do venv abre o interpretador como filho.
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn start(app: &AppHandle) -> Result<(), String> {
    if healthy() {
        open_hub(app);
        return Ok(());
    }

    let resources = app
        .path()
        .resource_dir()
        .map_err(|e| format!("Pasta do programa não encontrada: {e}"))?;
    let data = app
        .path()
        .app_local_data_dir()
        .map_err(|e| format!("Pasta de dados não encontrada: {e}"))?;
    let logs = data.join("logs");
    fs::create_dir_all(&logs).map_err(|e| format!("Não consegui criar {}: {e}", logs.display()))?;

    let hub_dir = resources.join("hub");
    let web_dir = resources.join("web");
    let venv = data.join("venv");

    prepare_venv(app, &resources.join("bin").join(UV_EXE), &hub_dir, &venv, &data, &logs)?;

    status(app, "Iniciando o Cordyhome…", false);
    let log_path = logs.join("cordyhome.log");
    let log = File::create(&log_path).map_err(|e| e.to_string())?;
    let mut cmd = Command::new(venv_python(&venv));
    cmd.args(["-m", "cordyhome"])
        .current_dir(&data)
        .env("PYTHONPATH", &hub_dir)
        .env("PYTHONUNBUFFERED", "1")
        .env("CORDYHOME_WEB", &web_dir)
        .env("CORDYHOME_PORT", PORT.to_string())
        .stdin(Stdio::null())
        .stdout(log.try_clone().map_err(|e| e.to_string())?)
        .stderr(log);
    let child = spawn_group(&mut cmd).map_err(|e| format!("Não consegui iniciar o hub: {e}"))?;
    *app.state::<HubProcess>().0.lock().unwrap() = Some(child);

    let deadline = Instant::now() + Duration::from_secs(90);
    while Instant::now() < deadline {
        if healthy() {
            open_hub(app);
            return Ok(());
        }
        let exited = app
            .state::<HubProcess>()
            .0
            .lock()
            .unwrap()
            .as_mut()
            .and_then(|c| c.try_wait().ok().flatten())
            .is_some();
        if exited {
            return Err(format!(
                "O hub parou ao iniciar.\n\n{}\n\nLog completo: {}",
                tail(&log_path, 15),
                log_path.display()
            ));
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    Err(format!("O hub não respondeu a tempo. Log: {}", log_path.display()))
}

/// Cria ou atualiza o venv quando o uv.lock embutido muda (nova versão do app).
fn prepare_venv(
    app: &AppHandle,
    uv: &Path,
    hub_dir: &Path,
    venv: &Path,
    data: &Path,
    logs: &Path,
) -> Result<(), String> {
    let lock = fs::read(hub_dir.join("uv.lock")).map_err(|e| format!("uv.lock ausente: {e}"))?;
    let stamp = data.join("venv.lock");
    if venv_python(venv).exists() && fs::read(&stamp).ok().as_deref() == Some(lock.as_slice()) {
        return Ok(());
    }

    status(
        app,
        "Preparando o Cordyhome. Na primeira vez isso leva alguns minutos, porque o Python é baixado.",
        false,
    );
    let log_path = logs.join("preparacao.log");
    let log = File::create(&log_path).map_err(|e| e.to_string())?;
    let mut cmd = Command::new(uv);
    cmd.args(["sync", "--frozen", "--no-dev", "--no-install-project", "--python", "3.12"])
        .arg("--project")
        .arg(hub_dir)
        .env("UV_PROJECT_ENVIRONMENT", venv)
        .env("UV_PYTHON_PREFERENCE", "only-managed")
        .stdin(Stdio::null())
        .stdout(log.try_clone().map_err(|e| e.to_string())?)
        .stderr(log);
    hide_console(&mut cmd);
    let result = cmd
        .status()
        .map_err(|e| format!("Não consegui rodar o uv ({}): {e}", uv.display()))?;
    if !result.success() {
        return Err(format!(
            "Falha ao preparar o Python. Verifique a internet e abra o Cordyhome de novo.\n\n{}\n\nLog completo: {}",
            tail(&log_path, 15),
            log_path.display()
        ));
    }
    fs::write(&stamp, &lock).map_err(|e| e.to_string())?;
    Ok(())
}

fn healthy() -> bool {
    let addr = SocketAddr::from(([127, 0, 0, 1], PORT));
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_secs(1)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    if stream
        .write_all(b"GET /api/health HTTP/1.0\r\nHost: localhost\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut buf = [0u8; 16];
    let n = stream.read(&mut buf).unwrap_or(0);
    let head = String::from_utf8_lossy(&buf[..n]);
    head.starts_with("HTTP/") && head.contains(" 200")
}

fn open_hub(app: &AppHandle) {
    crate::diag::log("Hub respondendo; abrindo a interface");
    READY.store(true, Ordering::SeqCst);
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.navigate(url());
    } else if USE_BROWSER.load(Ordering::SeqCst) {
        crate::open_in_browser(app);
    }
}

fn status(app: &AppHandle, message: &str, error: bool) {
    if !error {
        crate::diag::log(message);
    }
    if let Some(window) = app.get_webview_window("main") {
        let text = serde_json::to_string(message).unwrap_or_default();
        let _ = window.eval(format!("window.setStatus && window.setStatus({text}, {error})"));
    }
}

fn tail(path: &Path, lines: usize) -> String {
    let content = fs::read_to_string(path).unwrap_or_default();
    let all: Vec<&str> = content.lines().collect();
    all[all.len().saturating_sub(lines)..].join("\n")
}
