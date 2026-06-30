目前业界最主流的开源 MQTT Broker 有两款：

1. **EMQX**：国产开源之光，支持海量并发，自带非常漂亮且强大的可视化 Web 控制台，**极其推荐**。
2. **Eclipse Mosquitto**：极其轻量级，适合资源受限的单机小服务器，但默认没有可视化界面。

下面提供 **使用 Docker 部署 EMQX** 的极简完整流程。

---

### 🛠️ 准备工作

1. 一台拥有公网 IP 的云服务器（如阿里云、腾讯云等），操作系统推荐 Ubuntu/Debian/CentOS。
2. 服务器上已安装 **Docker**（如果还没装，可以搜一下“Ubuntu 安装 Docker”的极简教程）。
3. 在云服务器的安全组（防火墙）中放行以下端口：
* **1883**：MQTT 协议默认端口（设备端用这个连）。
* **18083**：EMQX Web 控制台端口（你在浏览器用这个看）。



---

### 🚀 部署流程（Docker 版）

#### 第一步：一键拉取并运行 EMQX 容器

通过 SSH 登录到你的云服务器，直接执行以下命令：

```bash
docker run -d --name emqx \
  -p 10010:18083 \
  -p 10011:1883 \
  -p 10012:8883 \
  -p 10013:8083 \
  -p 10014:8084 \
  emqx/emqx:latest
# -p {服务器端口}:{docker内部端口}，完成端口映射

docker update --restart always emqx # docker守护进程，保证服务持续运行
```

*这行命令会从后台下载并启动 EMQX，并将必要的端口映射到你的物理服务器上。*

#### 第二步：登录 Web 可视化控制台

打开你的浏览器，访问：`http://<你的服务器公网IP>:10010` （`http://36.112.105.170:10010`）

* **默认账号**：`admin`
* **默认密码**：`public`
*(首次登录会强制要求你修改密码，请务必记好新密码。)*

进入控制台后，你会看到一个非常直观的仪表盘（Dashboard），这里可以看到当前有多少设备连接、消息吞吐量等。

#### 第三步：为你的设备创建认证账号（重要）

为了防止别人恶意连接你的 Broker，必须开启密码认证。

1. 在 EMQX 控制台左侧菜单，找到 **访问控制 (Access Control)** -> **客户端认证 (Authentication)**。
2. 点击 **创建 (Create)**，选择 **Password-Based**，数据源选择 **Built-in Database**，一路点击下一步完成创建。
3. 创建完成后，点击这个认证列表里的 **用户管理 (Users)**。
4. 添加一个给设备用的账号，例如：
* **Username**: `device_01`
* **Password**: `my_secure_password`



---

### 🔌 修改你的 Python 代码

部署完成后，你只需要在运行 Python 代码的环境中，修改一下`config.yaml`，指向你的新服务器即可：

```bash
export MQTT_HOST="你的服务器公网IP"
export MQTT_PORT="1883"
export MQTT_USERNAME="device_01"
export MQTT_PASSWORD="my_secure_password"
# 重新运行你的 Python 程序

```

当代码运行后，你去 EMQX 控制台的 **客户端 (Clients)** 页面，就能实时看到你的 Python 脚本（设备）已经成功连接上来了！而且因为是直连你自己的服务器，**之前的物理网络延迟会被压缩到极限（国内同城或临近省份通常在 10ms - 30ms 左右）**。
