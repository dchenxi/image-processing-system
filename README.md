# 基于 Flask 与 OpenCV 的数字图像处理算法集成系统

一个 B/S 架构的 Web 端图像处理演示平台：浏览器上传图片、选择算法、调参数，服务端用 OpenCV 完成运算，前端并排显示原图与结果并支持下载。

## 功能

集成四大类共 19 种算法：

- 几何运算：平移、旋转、缩放、镜像、剪切、代数运算
- 对比度增强：Gamma 变换、直方图均衡化、拉普拉斯锐化
- 平滑处理：频率域低通滤波、均值滤波、中值滤波、高斯滤波
- 图像分割：Canny、Sobel、Otsu、自适应阈值、分水岭、K-Means

## 环境

- Python 3.13（Windows 11 下开发与测试）
- Flask 3.1.3、Werkzeug 3.1.9、opencv-python 5.0.0.93、NumPy 2.5.4

## 启动

```bash
cd image_processing_system
python -m venv .venv
.venv\Scripts\activate          # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

浏览器打开 http://127.0.0.1:5000 ，点击或拖拽上传 JPG / PNG / BMP 图像即可进入工作台。

## 目录结构

```
app.py                 # 路由、会话与算法调度
requirements.txt       # 依赖清单（pip install -r requirements.txt）
templates/             # 由 Flask 渲染的页面模板
  index.html           # 欢迎页：图像上传
  workspace.html       # 工作台：菜单、参数面板与双屏对比
static/                # 运行时目录，仓库中不提交
  uploads/             # 原始图像（UUID 命名）
  results/             # 处理结果（一请求一文件）
```

`static/uploads/` 与 `static/results/` 不需要手动创建：`app.py` 在启动时通过 `os.makedirs(..., exist_ok=True)` 自动生成；这两个目录存放用户上传与处理结果，已写入 `.gitignore`，因此**仓库里看不到它们属于正常现象**，克隆后首次运行会自动补齐。

同理，`.secret_key`（会话密钥）也在首次运行时生成并已被忽略，如果使用环境变量 `FLASK_SECRET_KEY` 甚至不会产生该文件。

## 配置

会话密钥不再硬编码：优先读取环境变量 `FLASK_SECRET_KEY`，否则首次运行时在项目根目录生成 `.secret_key`（已列入 `.gitignore`）。

## 说明

本项目为数字图像处理课程实践作业，侧重算法演示与参数交互，未包含用户体系与结果清理机制。
