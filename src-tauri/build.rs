fn main() {
    let suffix = if std::env::var("CARGO_CFG_TARGET_OS").unwrap() == "windows" {
        ".exe"
    } else {
        ""
    };
    let sidecar = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").unwrap())
        .join(format!("binaries/bookskill-sidecar{suffix}"));
    if !sidecar.exists() {
        panic!("Build Python sidecar first: python desktop/build_sidecar.py");
    }
    println!("cargo:rerun-if-changed={}", sidecar.display());
    println!("cargo:rustc-env=BOOKSKILL_SIDECAR={}", sidecar.display());
    tauri_build::build()
}
