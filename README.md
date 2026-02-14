# 🛡️ Monad Node Watchdog

**A lightweight, self-hosted monitoring tool for Monad Node Operators.**

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Monad](https://img.shields.io/badge/Network-Monad-purple)

## 📖 Overview
As a node operator, relying solely on third-party explorers for monitoring is risky. **Monad Node Watchdog** is a Python script designed to run locally alongside your node. It communicates directly with the RPC endpoint and sends instant **Telegram Alerts** if critical issues are detected.

### ✨ Features
* **Real-time Monitoring:** Checks block height and sync status every minute.
* **Stall Detection:** Alerts if block production halts (node stuck).
* **Sync Status:** Warns if the node falls behind the network (`catching_up` status).
* **Lightweight:** Uses minimal system resources (ideal for bare metal or VPS).
* **Privacy Focused:** No external data leaks; connects only to your local RPC and Telegram API.

---

## 🚀 Installation & Usage

### 1. Clone the Repository
```bash
git clone [https://github.com/bozdemir52/monad-node-watchdog.git](https://github.com/bozdemir52/monad-node-watchdog.git)
cd monad-node-watchdog
