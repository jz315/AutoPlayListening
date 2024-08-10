#include <windows.h>
#include <string>
#include <iostream>
#include <filesystem>

std::string get_file_path() {
    char buffer[MAX_PATH];
    GetModuleFileNameA(NULL, buffer, MAX_PATH);
    return std::filesystem::path(buffer).parent_path().string();
}

void add_to_startup() {
    std::string script_path = get_file_path();
    const char* key = "Software\\Microsoft\\Windows\\CurrentVersion\\Run";

    HKEY hKey;
    LONG result = RegOpenKeyExA(HKEY_CURRENT_USER, key, 0, KEY_SET_VALUE, &hKey);

    if (result != ERROR_SUCCESS) {
        std::cerr << "Failed to open registry key: " << result << std::endl;
        return;
    }

    const char* value_name = "Automatic Playback Hearing System";
    std::string value_data = script_path + "\\main.exe";

    result = RegSetValueExA(hKey, value_name, 0, REG_SZ,
                            (const BYTE*)value_data.c_str(),
                            value_data.length() + 1);

    if (result != ERROR_SUCCESS) {
        std::cerr << "Failed to set registry value: " << result << std::endl;
    } else {
        std::cout << "Successfully added to startup" << std::endl;
    }

    RegCloseKey(hKey);
}

int main() {
    add_to_startup();
    return 0;
}