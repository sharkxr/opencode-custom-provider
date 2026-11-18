 <div align="center">

<img src="assets/ocp-banner.png" alt="OCP — OpenCode Custom Provider" width="80%">

### OpenCode Custom Provider

**A better way to manage your OpenCode providers.**

A lightweight, elegant desktop application that makes configuring AI providers and models in [OpenCode](https://opencode.ai) simple, visual, and effortless.

<br>

[![License](https://img.shields.io/github/license/sharkxr/opencode-custom-provider?style=for-the-badge&color=white&labelColor=181818)](https://github.com/sharkxr/opencode-custom-provider/blob/main/LICENSE)
![Windows](https://img.shields.io/badge/Windows-Desktop-white?style=for-the-badge&logo=windows&logoColor=white&labelColor=181818)
![Python](https://img.shields.io/badge/Python-3.10%2B-white?style=for-the-badge&logo=python&logoColor=white&labelColor=181818)
![OpenCode](https://img.shields.io/badge/OpenCode-Compatible-white?style=for-the-badge&labelColor=181818)

<br>

[![Stars](https://img.shields.io/github/stars/sharkxr/opencode-custom-provider?style=flat-square&color=888888&labelColor=181818)](https://github.com/sharkxr/opencode-custom-provider/stargazers)
[![Forks](https://img.shields.io/github/forks/sharkxr/opencode-custom-provider?style=flat-square&color=888888&labelColor=181818)](https://github.com/sharkxr/opencode-custom-provider/forks)
[![Issues](https://img.shields.io/github/issues/sharkxr/opencode-custom-provider?style=flat-square&color=888888&labelColor=181818)](https://github.com/sharkxr/opencode-custom-provider/issues)
[![Last Commit](https://img.shields.io/github/last-commit/sharkxr/opencode-custom-provider?style=flat-square&color=888888&labelColor=181818)](https://github.com/sharkxr/opencode-custom-provider/commits/main)

<br>

[**Features**](#-features) · [**Getting Started**](#-getting-started) · [**Build**](#-build-from-source) · [**License**](#-license)

</div>

---

## ◈ Overview

**OCP (OpenCode Custom Provider)** takes the complexity out of editing your OpenCode configuration.

Forget manually navigating JSON files, typing provider configurations, and looking up model IDs.

OCP provides a clean, intuitive graphical interface to manage everything in one place.

> **Less configuration. More creation.**

## ✦ Features

| Feature | Description |
|:---|:---|
| **Automatic Detection** | Automatically locates your `opencode.json` configuration. |
| **Provider Management** | Add, edit, and remove custom AI providers. |
| **API Configuration** | Configure API keys and custom Base URLs. |
| **Model Discovery** | Fetch available models directly from compatible provider APIs. |
| **Manual Model Setup** | Add models individually using their model IDs. |
| **Portable Application** | Build a standalone Windows executable. |
| **Bilingual Interface** | Switch between English and Russian. |
| **Safe Configuration Saving** | Validates configurations and protects against conflicting file changes. |
| **Minimalist UI** | A modern, dark interface designed for simplicity. |

---

## ⚡ Getting Started

### 01. Get OCP

Download an available build from the [Releases page](https://github.com/sharkxr/opencode-custom-provider/releases), or build the application from source using the instructions below.

### 02. Open the application

Launch `OCP.exe`.

OCP automatically looks for your OpenCode configuration at:

```text
C:\Users\<username>\.config\opencode\opencode.json
```

You can also manually select your opencode.json configuration file.

### 03. Configure your providers

1. Click **Add Provider**.
2. Enter a provider name.
3. Specify your **API Key** and **Base URL**.
4. Add model IDs manually or fetch models from the provider.
5. Select the models you want and save.

**That's it. Your OpenCode configuration is ready.**

---

## ◈ Model Discovery

OCP can retrieve a provider's available models through a compatible API endpoint.

Instead of manually searching for model identifiers:

- Enter your provider's Base URL.
- Choose **Load from Server**.
- Browse and search the returned models.
- Select the models you want to add.

> Model discovery requires a compatible provider API. Support may vary depending on the provider.

---

## 🛠 Build from Source

OCP is built with **Python and PyQt6**.

### Requirements

- Windows
- Python 3.10 or newer
- Internet connection for installing dependencies

### Clone the repository

```bash
git clone https://github.com/sharkxr/opencode-custom-provider.git
cd opencode-custom-provider
```

### Run from source

```bash
pip install "PyQt6>=6.7,<7" "requests>=2.32,<3"
python main.py
```

### Build a portable EXE

Run the included build script:

```bat
build.bat
```

The script installs the required build dependencies and packages OCP using PyInstaller.

The resulting executable will be available at:

```text
dist\OCP.exe
```

No Python installation is required to run the built executable.

---

## 📁 Project Structure

```text
opencode-custom-provider/
│
├── main.py           # Application source
├── build.bat         # Windows build script
├── LICENSE           # Apache License 2.0
├── README.md         # Documentation
│
└── assets/
    └── ocp-banner.png
```

*The `assets` directory contains the optional README banner.*

---

## 🤝 Contributing

Contributions, suggestions, and improvements are welcome!

If you have an idea or find a bug:

- Open an [Issue](https://github.com/sharkxr/opencode-custom-provider/issues).
- Submit a [Pull Request](https://github.com/sharkxr/opencode-custom-provider/pulls).
- Help improve the application or its documentation.

Every contribution helps make OCP better.

---

## ⚖ License

Distributed under the **Apache License 2.0**.

You are free to use, modify, and distribute this software under the terms of the license.

See the [LICENSE](https://github.com/sharkxr/opencode-custom-provider/blob/main/LICENSE) file for details.

---

<div align="center">

### Made for the OpenCode community.

**Simple. Lightweight. Open Source.**

Created by [**@sharkxr**](https://github.com/sharkxr)

<br>

<a href="https://github.com/sharkxr/opencode-custom-provider">
  <img src="https://img.shields.io/badge/Explore_the_Repository-181818?style=for-the-badge&logo=github&logoColor=white" alt="Explore Repository">
</a>

<br><br>

**If you find OCP useful, consider giving the repository a ⭐**

<sub>OCP is an independent project for OpenCode.</sub>

</div>

