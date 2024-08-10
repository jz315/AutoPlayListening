use std::fs;
use std::fs::File;
use std::io::{self, Write, Read, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, exit};
use std::env;
use std::error::Error;
use std::sync::Mutex;
use reqwest::blocking::get;
use serde::{Deserialize, Serialize};
use log4rs::append::file::FileAppender;
use log4rs::config::{self, Appender, Root};
use log4rs::encode::pattern::PatternEncoder;

use tempfile::NamedTempFile;
use zip::read::ZipArchive;
use log::{error, info };
#[derive(Deserialize)]
struct Release {
    tag_name: String,
    zipball_url: String,
}

#[derive(Serialize, Deserialize)]
struct Config {
    version: String,
}

fn get_latest_release() -> Result<(String, String), Box<dyn Error>> {
    let url = "https://api.github.com/repos/jz315/AutoPlayListening/releases/latest";
    let response = get(url)?;
    
    if response.status().is_success() {
        let release_data: Release = response.json()?;
        Ok((release_data.tag_name, release_data.zipball_url))
    } else {
        error!("Failed to fetch the latest release. Status code: {}", response.status());
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
    let config = Config { version: version.to_string() };
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
    if let Ok(exec_path) = env::current_exe() {
        exec_path.parent().unwrap().to_path_buf()
    } else {
        env::current_dir().unwrap()
    }
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

        info!("Download complete. Applying update...");
        apply_update(temp_file.path(), &get_file_path())?;

        write_version(config_path, &latest_version)?;

        info!("Update applied. Restarting application...");

    } else {
        info!("No updates available.");
    }

    Ok(())
}

fn main() {
    let config_path = Path::new("config.json");
    // 配置日志记录器
    let logfile = FileAppender::builder()
        .encoder(Box::new(PatternEncoder::new("{l} - {m}\n")))
        .build("updater.log")
        .unwrap();

    let config = config::Config::builder()
        .appender(Appender::builder().build("logfile", Box::new(logfile)))
        .build(Root::builder().appender("logfile").build(log::LevelFilter::Info))
        .unwrap();

    log4rs::init_config(config).unwrap();
    if let Err(e) = auto_update(config_path) {
        error!("Update failed: {}", e);
    }
}
