import cv2
import glob
import time

def test_cameras():
    print("🔍 开始扫描 /dev/v4l/by-id/ 下的相机设备...\n")
    
    # 查找所有 v4l by-id 路径（优先测试 index0 和 index0 的主数据流）
    cam_paths = glob.glob('/dev/v4l/by-id/*')
    
    if not cam_paths:
        print("⚠️ 未在 /dev/v4l/by-id/ 下找到设备，尝试扫描 /dev/video* ...")
        cam_paths = glob.glob('/dev/video*')

    # 过滤一下，通常包含 index0 的才是主 RGB/Depth 节点
    test_paths = [p for p in cam_paths if 'index0' in p]
    if not test_paths: # 如果没有 index0，就全测
        test_paths = cam_paths

    for path in sorted(test_paths):
        print(f"👉 正在测试接口: {path.split('/')[-1]}")
        
        # 强制使用 V4L2 后端，避免 Linux 下的 GStreamer 警告卡死
        cap = cv2.VideoCapture(path, cv2.CAP_V4L2)
        
        if not cap.isOpened():
            print(f"   ❌ 失败: 无法建立连接 (设备不存在或没有权限)\n")
            continue

        # 等待相机的自动曝光和初始化，给点缓冲时间
        time.sleep(0.5) 
        
        # 尝试读取一帧画面
        ret, frame = cap.read()
        
        if ret:
            print(f"   ✅ 成功: 成功读取数据流！(分辨率: {frame.shape[1]}x{frame.shape[0]})\n")
        else:
            print(f"   ❌ 失败: 端口已打开，但无法抓取画面 (极可能是被占用或硬件假死)\n")
            
        cap.release()

if __name__ == "__main__":
    test_cameras()