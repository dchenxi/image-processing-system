import os
import secrets
import time
import uuid

import cv2
import numpy as np
from flask import Flask, render_template, request, session, jsonify, send_from_directory, redirect, url_for

app = Flask(__name__)


def load_secret_key():
    """读取会话密钥：优先环境变量，其次本地密钥文件，最后自动生成。

    这样密钥不再硬编码在源码里，可以直接公开仓库；
    生成的 .secret_key 已在 .gitignore 中排除，不会进入版本库。
    """
    key = os.environ.get('FLASK_SECRET_KEY')
    if key:
        return key

    key_file = os.path.join(app.root_path, '.secret_key')
    try:
        if os.path.exists(key_file):
            with open(key_file, 'r', encoding='utf-8') as f:
                key = f.read().strip()
            if key:
                return key
        key = secrets.token_hex(32)
        with open(key_file, 'w', encoding='utf-8') as f:
            f.write(key)
        return key
    except OSError:
        # 无写入权限时退化为进程内随机密钥，仅本次运行有效
        return secrets.token_hex(32)


app.secret_key = load_secret_key()

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
RESULT_FOLDER = os.path.join(app.root_path, 'static', 'results')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULT_FOLDER'] = RESULT_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def cv_imread(file_path):
    return cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)

def cv_imwrite(file_path, img):
    ext = os.path.splitext(file_path)[1]
    cv2.imencode(ext, img)[1].tofile(file_path)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return "没有文件", 400
    file = request.files['file']
    if file.filename == '': return "没有选择文件", 400
    if file and allowed_file(file.filename):
        ext = os.path.splitext(file.filename)[1].lower()
        new_filename = f"img_{uuid.uuid4().hex[:8]}{ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
        session['current_image'] = new_filename
        return redirect(url_for('workspace'))
    return "不支持的文件格式", 400

@app.route('/workspace')
def workspace():
    if 'current_image' not in session: return redirect(url_for('index'))
    return render_template('workspace.html', image=session['current_image'])

@app.route('/process', methods=['POST'])
def process_image():
    if 'current_image' not in session: return jsonify({'error': '请先上传图片'}), 400
    
    data = request.json
    algorithm = data.get('algorithm')
    
    img_path = os.path.join(app.config['UPLOAD_FOLDER'], session['current_image'])
    img = cv_imread(img_path)
    if img is None: return jsonify({'error': '读取图片失败'}), 500

    start_time = time.time()

    # ================= 算法处理区 =================
    try:
        # ---------- 1. 基本运算 ----------
        if algorithm == 'translate':
            tx = int(data.get('tx', 50))
            ty = int(data.get('ty', 50))
            M = np.float32([[1, 0, tx], [0, 1, ty]])
            result_img = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]))

        elif algorithm == 'rotate':
            angle = float(data.get('angle', 45))
            h, w = img.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            result_img = cv2.warpAffine(img, M, (w, h))
            
        elif algorithm == 'scale':
            scale = float(data.get('scale', 0.5))
            interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
            result_img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)

        elif algorithm == 'flip':
            flip_code = int(data.get('flip_code', 1))
            result_img = cv2.flip(img, flip_code)

        elif algorithm == 'shear':
            sx = float(data.get('shear_x', 0.2))
            sy = float(data.get('shear_y', 0.0))
            M = np.float32([[1, sx, 0], [sy, 1, 0]])
            result_img = cv2.warpAffine(img, M, (int(img.shape[1] + img.shape[0]*sx), int(img.shape[0] + img.shape[1]*sy)))

        elif algorithm == 'arithmetic_add':
            # 算术运算：加法（调整亮度）
            value = int(data.get('value', 50))
            result_img = np.clip(img.astype(int) + value, 0, 255).astype(np.uint8)

        # ---------- 2. 图像增强 ----------
        elif algorithm == 'hist_eq':
            img_y_cr_cb = cv2.cvtColor(img, cv2.COLOR_BGR2YCrCb)
            y, cr, cb = cv2.split(img_y_cr_cb)
            result_img = cv2.cvtColor(cv2.merge([cv2.equalizeHist(y), cr, cb]), cv2.COLOR_YCrCb2BGR)
            
        elif algorithm == 'gamma':
            gamma = float(data.get('gamma', 1.5))
            inv_gamma = 1.0 / gamma
            table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
            result_img = cv2.LUT(img, table)

        elif algorithm == 'laplacian_sharpen':
            # 图像锐化：拉普拉斯算子
            strength = float(data.get('strength', 1.0))
            kernel = np.array([[0, -1, 0], 
                               [-1, 5, -1], 
                               [0, -1, 0]])
            # 使用自定义核进行滤波实现锐化
            result_img = cv2.filter2D(img, -1, kernel * strength if strength != 1.0 else kernel)

        # ---------- 3. 图像平滑 ----------
        elif algorithm == 'mean_blur':
            ksize = int(data.get('ksize', 3))
            if ksize % 2 == 0: ksize += 1
            result_img = cv2.blur(img, (ksize, ksize))

        elif algorithm == 'median_blur':
            ksize = int(data.get('ksize', 3))
            if ksize % 2 == 0: ksize += 1
            result_img = cv2.medianBlur(img, ksize)

        elif algorithm == 'gaussian_blur':
            ksize = int(data.get('ksize', 3))
            if ksize % 2 == 0: ksize += 1
            result_img = cv2.GaussianBlur(img, (ksize, ksize), 0)

        elif algorithm == 'fft_lowpass':
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            d0 = int(data.get('d0', 30))
            rows, cols = gray.shape
            crow, ccol = rows // 2, cols // 2
            f = np.fft.fft2(gray)
            fshift = np.fft.fftshift(f)
            mask = np.zeros((rows, cols), np.uint8)
            mask[crow-d0:crow+d0, ccol-d0:ccol+d0] = 1
            fshift = fshift * mask
            f_ishift = np.fft.ifftshift(fshift)
            img_back = np.fft.ifft2(f_ishift)
            result_img = cv2.normalize(np.abs(img_back), None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

        # ---------- 4. 图像分割 ----------
        elif algorithm == 'canny':
            low = int(data.get('low', 50))
            high = int(data.get('high', 150))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            result_img = cv2.Canny(gray, low, high)

        elif algorithm == 'sobel':
            ksize = int(data.get('ksize', 3))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # 分别计算x和y方向的梯度
            grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=ksize)
            grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=ksize)
            # 合并梯度
            abs_grad_x = cv2.convertScaleAbs(grad_x)
            abs_grad_y = cv2.convertScaleAbs(grad_y)
            result_img = cv2.addWeighted(abs_grad_x, 0.5, abs_grad_y, 0.5, 0)

        elif algorithm == 'otsu':
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, result_img = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        elif algorithm == 'adaptive_thresh':
            # 自适应阈值分割
            block_size = int(data.get('block_size', 11))
            if block_size % 2 == 0: block_size += 1
            c = int(data.get('c', 2))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            result_img = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c)

        elif algorithm == 'watershed':
            # 分水岭算法（简化版演示：利用形态学距离变换寻找标记）
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            ret, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            
            # 形态学开运算去噪
            kernel = np.ones((3,3), np.uint8)
            opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)
            # 确定背景区域
            sure_bg = cv2.dilate(opening, kernel, iterations=3)
            # 寻找前景区域
            dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
            ret, sure_fg = cv2.threshold(dist_transform, 0.7 * dist_transform.max(), 255, 0)
            # 寻找未知区域
            sure_fg = np.uint8(sure_fg)
            unknown = cv2.subtract(sure_bg, sure_fg)
            # 标记
            ret, markers = cv2.connectedComponents(sure_fg)
            markers = markers + 1
            markers[unknown == 255] = 0
            # 分水岭变换
            markers = cv2.watershed(img, markers)
            # 将边界标记为红色
            result_img = img.copy()
            result_img[markers == -1] = [0, 0, 255]

        elif algorithm == 'kmeans_region':
            k = int(data.get('k', 3))
            data_float = np.float32(img.reshape((-1, 3)))
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            _, labels, centers = cv2.kmeans(data_float, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
            centers = np.uint8(centers)
            res = centers[labels.flatten()]
            result_img = res.reshape(img.shape)

        else:
            return jsonify({'error': '未知的算法'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    # ==============================================

    ext = os.path.splitext(session['current_image'])[1]
    result_filename = f"res_{uuid.uuid4().hex[:8]}{ext}"
    cv_imwrite(os.path.join(app.config['RESULT_FOLDER'], result_filename), result_img)

    elapsed_time = round((time.time() - start_time) * 1000, 2)

    return jsonify({
        'success': True,
        'result_url': f'/static/results/{result_filename}',
        'download_name': result_filename,
        'time': elapsed_time
    })

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(app.config['RESULT_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)