import cv2

# 正确的初始化方法：使用 cv2.VideoCapture 打开 /dev/video5
cap = cv2.VideoCapture(1)

if not cap.isOpened():
    print("无法打开相机节点 /dev/video5")
    exit()

# 读取一帧画面
ret, frame = cap.read()

if ret:
    # 保存为图片
    cv2.imwrite("camera_test.jpg", frame)
    print("图片已成功保存为 camera_test.jpg！")
else:
    print("相机已打开，但抓取画面失败。")

# 释放相机资源
cap.release()