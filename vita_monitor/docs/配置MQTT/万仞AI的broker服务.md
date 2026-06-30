# 北京-万仞 本地broker（仅测试用）

李靖服务器

仅限内网使用的broker管理界面：
网址：`http://192.168.1.36:10010/`
登录：
```
admin
wanrenai888!
```

# 云服务器broker

管理平台：[http://101.126.68.169:5002](http://101.126.68.169:5002)
broker通信：[http://101.126.68.169:5004](http://101.126.68.169:5004)

```
Host 万仞火山
  HostName 101.126.68.169
  Port 22
  User root
```

### 部署tips：

通过 SSH 登录到你的云服务器，直接执行以下命令：

```bash
docker run -d --name emqx \
  --net=host \
  --restart always \
  -e EMQX_DASHBOARD__LISTENERS__HTTP__BIND=5002 \
  -e EMQX_LISTENERS__TCP__DEFAULT__BIND=5004 \
  emqx/emqx:latest
# -p {服务器端口}:{docker内部端口}，完成端口映射
# docker守护进程，保证服务持续运行
```