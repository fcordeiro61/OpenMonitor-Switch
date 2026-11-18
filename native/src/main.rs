#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use slint::{CloseRequestResponse, ComponentHandle};

slint::include_modules!();

fn main() -> Result<(), slint::PlatformError> {
    let window = MainWindow::new()?;
    let tray = AppTray::new()?;

    // A bandeja continua visível quando a janela é fechada.
    window.window().on_close_requested(|| CloseRequestResponse::HideWindow);

    let window_weak = window.as_weak();
    window.on_hide_to_tray(move || {
        if let Some(window) = window_weak.upgrade() {
            let _ = window.hide();
        }
    });

    let window_weak = window.as_weak();
    tray.on_open_window(move || {
        if let Some(window) = window_weak.upgrade() {
            let _ = window.show();
        }
    });

    tray.on_exit_app(|| {
        let _ = slint::quit_event_loop();
    });

    tray.show()?;
    window.show()?;
    slint::run_event_loop()
}
