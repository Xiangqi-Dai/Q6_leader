# Supervisor 一键启动

本目录为 [Supervisor](http://supervisord.org/) 提供与本仓库配套的**启动脚本**与 **`conf.d` 程序片段**，用于在服务器或设备上一键拉起：

- **后端接收服务**：`backend_receiver/main.py`
- **硬件发送端**：`hardware_sender/main.py`

## 目录说明

| 路径 | 说明 |
|------|------|
| `scripts/` | 可被 Supervisor 或手工调用的 shell 启动脚本（内部会 `cd` 到对应子项目并**固定**执行 `/usr/bin/python main.py`） |
| `conf.d/` | 复制或软链到系统 Supervisor 的 `conf.d`（例如 `/etc/supervisor/conf.d/`）后，由 `supervisord` 加载的程序定义 |

## 使用前准备

1. 已安装 Supervisor，且主配置中包含类似：

   ```ini
   [include]
   files = /etc/supervisor/conf.d/*.conf
   ```

2. 本仓库路径在机器上固定后，将 `conf.d/*.conf` 中的占位符 **`@@REPO_ROOT@@`** 全部替换为该仓库的**绝对路径**（无尾部斜杠）。例如：

   ```bash
   sed -i 's|@@REPO_ROOT@@|/opt/Embodied-Intelligence-Body-Vital-Signs-Monitoring-System|g' conf.d/*.conf
   ```

3. Python 环境：脚本**固定使用** `/usr/bin/python`。请安装两套依赖（任选一种方式即可）：

   **方式 A（推荐，Supervisor 以 root 运行时最省事）——系统级 site-packages：**

   ```bash
   sudo /usr/bin/python -m pip install -r "$REPO_ROOT/backend_receiver/requirements.txt"
   sudo /usr/bin/python -m pip install -r "$REPO_ROOT/hardware_sender/requirements.txt"
   ```

   **方式 B——当前登录用户 `pip install --user`（包在 `~/.local`）：**  
   手工登录执行与上面相同命令但加 `--user` 即可。若 **supervisord 以 root 启动**，root 下的 Python **默认看不到**你的 `~/.local`，请在对应 `[program:...]` 中增加一行（把家目录改成你的部署用户）：

   ```ini
   environment=EMBODIED_USER_SITE_HOME="/home/wanren"
   ```

   启动脚本会把其转换为 `PYTHONUSERBASE=/home/wanren/.local`，从而加载该用户用 `/usr/bin/python` 安装的包。

   若系统仅有 `python3` 而无 `python`，需安装 `python-is-python3` 或自行建立 `/usr/bin/python` 到 `python3` 的符号链接。

4. 日志目录：`conf.d` 中日志写在 `@@REPO_ROOT@@/supervisor_conf/logs/`。首次部署可执行：

   ```bash
   mkdir -p "$REPO_ROOT/supervisor_conf/logs"
   ```

## 安装 conf 并重载

```bash
sudo cp conf.d/*.conf /etc/supervisor/conf.d/
# 或 sudo ln -sf "$REPO_ROOT/supervisor_conf/conf.d/"*.conf /etc/supervisor/conf.d/
sudo supervisorctl reread
sudo supervisorctl update
```

## 手工启动（不经过 Supervisor）

```bash
chmod +x scripts/*.sh
./scripts/start_backend_receiver.sh
./scripts/start_hardware_sender.sh
```

可选参数会原样传给 `main.py`（例如 `--config /path/to/config.yaml`）。

## 程序名（supervisorctl）

- 后端：`embodied-vita-monitor-backend-receiver`
- 硬件端：`embodied-vita-monitor-hardware-sender`

```bash
sudo supervisorctl status embodied-vita-monitor-backend-receiver embodied-vita-monitor-hardware-sender
sudo supervisorctl restart embodied-vita-monitor-backend-receiver
```
