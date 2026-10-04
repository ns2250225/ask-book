#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use sha2::{Digest, Sha256};
use std::{
    fs,
    io::Write,
    net::TcpStream,
    path::Path,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

const SIDECAR: &[u8] = include_bytes!(env!("BOOKSKILL_SIDECAR"));
const PORT: u16 = 17863; // Stable origin preserves IndexedDB settings across launches.

struct Backend {
    child: Child,
    token: String,
}
impl Drop for Backend {
    fn drop(&mut self) {
        if let Ok(mut stream) = TcpStream::connect(("127.0.0.1", PORT)) {
            let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));
            let _ = write!(stream, "POST /__desktop__/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{PORT}\r\nCookie: bookskill_session={}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", self.token);
        }
        let deadline = Instant::now() + Duration::from_secs(8);
        while Instant::now() < deadline {
            if matches!(self.child.try_wait(), Ok(Some(_))) {
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            let _ = Command::new("taskkill")
                .args(["/PID", &self.child.id().to_string(), "/T", "/F"])
                .creation_flags(0x08000000)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn start_backend(data: &Path) -> Result<(Backend, String), Box<dyn std::error::Error>> {
    fs::create_dir_all(data)?;
    // Refuse a competing server before replacing any executable or launching Python.
    if TcpStream::connect(("127.0.0.1", PORT)).is_ok() {
        return Err("本地端口 17863 已占用，请关闭已运行的问书或占用该端口的程序。".into());
    }
    let hash = format!("{:x}", Sha256::digest(SIDECAR));
    let runtime = data.join("runtime").join(&hash[..16]);
    fs::create_dir_all(&runtime)?;
    let executable = runtime.join(if cfg!(windows) {
        "bookskill-sidecar.exe"
    } else {
        "bookskill-sidecar"
    });
    if !executable.exists() || Sha256::digest(fs::read(&executable)?) != Sha256::digest(SIDECAR) {
        let temp = runtime.join("sidecar.tmp");
        fs::write(&temp, SIDECAR)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&temp, fs::Permissions::from_mode(0o700))?;
        }
        fs::rename(temp, &executable)?;
    }
    let token = uuid::Uuid::new_v4().simple().to_string();
    let ready = data.join(format!("ready-{}.txt", uuid::Uuid::new_v4()));
    let mut command = Command::new(&executable);
    command
        .arg("--data-dir")
        .arg(data)
        .arg("--ready-file")
        .arg(&ready)
        .arg("--port")
        .arg(PORT.to_string())
        .arg("--parent-pid")
        .arg(std::process::id().to_string())
        .env("BOOKSKILL_SESSION", &token)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW, including child launch.
    }
    let mut backend = Backend {
        child: command.spawn()?,
        token,
    };
    let deadline = Instant::now() + Duration::from_secs(90);
    while Instant::now() < deadline {
        if let Some(status) = backend.child.try_wait()? {
            return Err(format!(
                "Python 服务启动失败 ({status})，请查看 {}",
                data.join("desktop.log").display()
            )
            .into());
        }
        if ready.exists() {
            let origin = fs::read_to_string(&ready)?;
            fs::remove_file(&ready)?;
            return Ok((backend, origin));
        }
        thread::sleep(Duration::from_millis(100));
    }
    Err(format!(
        "Python 服务启动超时，请查看 {}",
        data.join("desktop.log").display()
    )
    .into())
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let app = tauri::Builder::default()
        .setup(|app| {
            let data = app.path().app_local_data_dir()?;
            let (backend, origin) = start_backend(&data)?;
            let url = format!("{origin}/__desktop__/start?token={}", backend.token);
            app.manage(Mutex::new(Some(backend)));
            let allowed_origin = origin.clone();
            let docs_origin = origin.clone();
            let docs_app = app.handle().clone();
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url.parse()?))
                .title("问书 · BookSkill")
                .inner_size(1280.0, 860.0)
                .min_inner_size(860.0, 600.0)
                .disable_drag_drop_handler()
                .on_navigation(move |url| {
                    if url.origin().ascii_serialization() == allowed_origin {
                        return true;
                    }
                    if matches!(url.scheme(), "https" | "http") {
                        let _ = open::that(url.as_str());
                    }
                    false
                })
                .on_new_window(move |url, _| {
                    if url.origin().ascii_serialization() == docs_origin {
                        let local_origin = docs_origin.clone();
                        if let Ok(window) = WebviewWindowBuilder::new(
                            &docs_app,
                            format!("docs-{}", uuid::Uuid::new_v4()),
                            WebviewUrl::External(url),
                        )
                        .title("问书 · API 文档")
                        .inner_size(1000.0, 760.0)
                        .on_navigation(move |url| {
                            url.origin().ascii_serialization() == local_origin
                        })
                        .build()
                        {
                            return tauri::webview::NewWindowResponse::Create { window };
                        }
                        return tauri::webview::NewWindowResponse::Deny;
                    }
                    if matches!(url.scheme(), "https" | "http") {
                        let _ = open::that(url.as_str());
                    }
                    tauri::webview::NewWindowResponse::Deny
                })
                .on_download(|_, event| {
                    if let tauri::webview::DownloadEvent::Requested { destination, .. } = event {
                        let name = destination
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .to_string();
                        if let Some(path) = rfd::FileDialog::new().set_file_name(name).save_file() {
                            *destination = path;
                        } else {
                            return false;
                        }
                    }
                    true
                })
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())?;
    app.run(|handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Some(state) = handle.try_state::<Mutex<Option<Backend>>>() {
                if let Ok(mut backend) = state.lock() {
                    backend.take();
                }
            }
        }
        // Closing the main window exits on macOS too, releasing the worker.
        if matches!(
            event,
            tauri::RunEvent::WindowEvent {
                event: tauri::WindowEvent::Destroyed,
                ref label,
                ..
            } if label == "main"
        ) {
            handle.exit(0);
        }
    });
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        rfd::MessageDialog::new()
            .set_title("问书启动失败")
            .set_description(error.to_string())
            .set_level(rfd::MessageLevel::Error)
            .show();
    }
}
