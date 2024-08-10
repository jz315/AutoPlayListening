use log4rs::append::file::FileAppender;
use log4rs::config::{self, Appender, Root};
use log4rs::encode::pattern::PatternEncoder;
use reqwest::blocking::{get, Client};
use reqwest::header::USER_AGENT;
use serde::{Deserialize, Serialize};
use std::env;
use std::error::Error;
use std::fs;
use std::fs::File;
use std::io::{self, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{exit, Command};
use std::sync::Mutex;
use std::thread::sleep;
use std::time::Duration;

use log::{error, info};
use tempfile::NamedTempFile;
use zip::read::ZipArchive;

#[derive(Deserialize)]
struct Asset {
    browser_download_url: String,
}

#[derive(Deserialize)]
struct Release {
    tag_name: String,
    assets: Vec<Asset>,
}

#[derive(Serialize, Deserialize)]
struct Config {
    version: String,
}

fn get_latest_release() -> Result<(String, String), Box<dyn Error>> {
    let url = "https://api.github.com/repos/jz315/AutoPlayListening/releases/latest";
    // 创建 reqwest 客户端
    let client = Client::new();

    // 设置请求头
    let response = client.get(url).header(USER_AGENT, "request").send()?;

    if response.status().is_success() {
        let release_data: Release = response.json()?;

        // 这里假设我们只取第一个资产的下载链接
        if let Some(first_asset) = release_data.assets.first() {
            info!(
                "Fetched latest release download URL: {}",
                first_asset.browser_download_url
            );
            Ok((
                release_data.tag_name,
                first_asset.browser_download_url.clone(),
            ))
        } else {
            Err("No assets found in the latest release".into())
        }
    } else {
        error!(
            "Failed to fetch the latest release. Status code: {}",
            response.status()
        );
        Err("Failed to fetch the latest release".into())
    }
}

fn read_version(config_path: &Path) -> Result<String, Box<dyn Error>> {
    let file = File::open(config_path)?;
    let reader = BufReader::new(file);
    let config: Config = serde_json::from_reader(reader)?;
    Ok(config.version)
}

fn write_version(config_path: &Path, version: &str) -> Result<(), Box<dyn Error>> {
    let config = Config {
        version: version.to_string(),
    };
    let file = File::create(config_path)?;
    serde_json::to_writer(file, &config)?;
    Ok(())
}

fn download_update(url: &str, destination_path: &Path) -> Result<(), Box<dyn Error>> {
    let mut response = get(url)?;
    let mut file = File::create(destination_path)?;
    io::copy(&mut response, &mut file)?;
    Ok(())
}

fn get_file_path() -> PathBuf {
    env::current_dir().unwrap()
}

fn apply_update(update_file: &Path, install_dir: &Path) -> Result<(), Box<dyn Error>> {
    let file = File::open(update_file)?;
    let mut archive = ZipArchive::new(file)?;
    archive.extract(install_dir)?;
    Ok(())
}

fn auto_update(config_path: &Path) -> Result<(), Box<dyn Error>> {
    let (latest_version, update_url) = get_latest_release()?;
    let current_version = read_version(config_path)?;

    if latest_version > current_version {
        info!("Update available. Downloading...");

        let temp_file = NamedTempFile::new()?;
        download_update(&update_url, temp_file.path())?;

        info!(
            "Download complete. Applying update to {}",
            get_file_path().to_str().unwrap()
        );
        apply_update(temp_file.path(), &get_file_path())?;

        write_version(config_path, &latest_version)?;

        info!("Update applied. Restarting application...");
    } else {
        info!("No updates available.");
    }

    Ok(())
}

fn swap_start() {
    let current_exe_path = env::current_exe().unwrap();
    let current_exe_name = current_exe_path.file_name().unwrap_or_default();

    if current_exe_name == "updater.exe" {
        
        let folder_path = env::current_dir().unwrap();

        let updater_path = folder_path.join("updater.exe");
        let updater_temp_path = folder_path.join("updater-temp.exe");

        // 检查是否既有 updater 和 updater-temp
        if updater_path.exists() && updater_temp_path.exists() {
            // 删除 updater-temp
            sleep(Duration::from_secs(1));

            match fs::remove_file(&updater_temp_path) {
                Ok(_) => println!("Successfully deleted file: {:?}", updater_temp_path.to_str()),
                Err(e) => println!("Failed to delete file: {:?}, error: {}", updater_temp_path.to_str(),e)}

            println!("process {} completed", std::process::id());
            return
        } else {
            println!("No action needed.");
        }
        // 1. 判断程序名为 updater
        let temp_exe_path = current_exe_path.with_file_name("updater-temp.exe");

        // 2. 复制程序为 updater-temp
        fs::copy(&current_exe_path, &temp_exe_path);

        // 3. 启动 updater-temp 并退出当前程序
        Command::new(temp_exe_path)
            .spawn()
            .expect("Failed to start updater-temp");
        println!("process {} completed", std::process::id());
        exit(0);
    } else if current_exe_name == "updater-temp.exe" {
        // 4. updater-temp 执行更新操作

        update();

        // 5. 启动原程序 updater
        let original_exe_path = current_exe_path.with_file_name("updater.exe");
        Command::new(original_exe_path)
            .spawn()
            .expect("Failed to start updater");

        println!("process {} completed", std::process::id());
        exit(0);
    } else {
        // 处理其他情况
        eprintln!("Unexpected program name");
        exit(1);
    }
}

fn update() {
    let config_path = Path::new("config.json");
    // 配置日志记录器
    let logfile = FileAppender::builder()
        .encoder(Box::new(PatternEncoder::new("{l} - {m}\n")))
        .build("updater.log")
        .unwrap();

    let config = config::Config::builder()
        .appender(Appender::builder().build("logfile", Box::new(logfile)))
        .build(
            Root::builder()
                .appender("logfile")
                .build(log::LevelFilter::Info),
        )
        .unwrap();

    log4rs::init_config(config).unwrap();
    if let Err(e) = auto_update(config_path) {
        error!("Update failed: {}", e);
    }
}
fn main() {
    swap_start()
}
