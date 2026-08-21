import sys
import os

import numpy as np
import pandas as pd
from PIL import Image

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QScrollArea,
    QFrame,
    QSizePolicy,
    QCheckBox
)

from PyQt6.QtGui import (
    QImage,
    QPixmap,
    QPainter,
    QPen,
    QColor
)

from PyQt6.QtCore import (
    Qt,
    pyqtSignal
)

import pyqtgraph as pg

from brightness_io import (
    BRIGHTNESS_HEIGHT,
    BRIGHTNESS_WIDTH,
    convert_brightness_bin_to_txt,
    validate_brightness_bin,
)


# ============================================================
# 图片显示控件
# ============================================================

class ImageViewer(QLabel):

    roiChanged = pyqtSignal(int, int, int, int)
    mousePixelChanged = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()

        self.image = None
        self.original_pixmap = None

        # 显示缩放比例
        self.scale_factor = 1.0

        # ROI使用原图坐标
        # x, y, width, height
        self.roi = None

        self.dragging = False

        self.start_point = None
        self.current_point = None

        self.setMouseTracking(True)

        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft |
            Qt.AlignmentFlag.AlignTop
        )

        self.setStyleSheet("""
            QLabel {
                background-color: #101318;
            }
        """)

    # ========================================================
    # 加载图片
    # ========================================================

    def load_image(self, image):

        self.image = image.copy()

        rgb = image

        h, w, channel = rgb.shape

        bytes_per_line = channel * w

        qimage = QImage(
            rgb.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_RGB888
        ).copy()

        self.original_pixmap = QPixmap.fromImage(qimage)

        self.scale_factor = 1.0
        self.roi = None

        self.update_display()

    # ========================================================
    # 更新图片
    # ========================================================

    def update_display(self):

        if self.original_pixmap is None:
            return

        width = max(
            1,
            int(
                self.original_pixmap.width()
                * self.scale_factor
            )
        )

        height = max(
            1,
            int(
                self.original_pixmap.height()
                * self.scale_factor
            )
        )

        # 这里虽然缩放显示，
        # 但数据计算始终使用原图坐标
        display_pixmap = self.original_pixmap.scaled(
            width,
            height,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        self.setPixmap(display_pixmap)

        self.setFixedSize(
            width,
            height
        )

        self.update()

    # ========================================================
    # 放大
    # ========================================================

    def zoom_in(self):

        if self.original_pixmap is None:
            return

        self.scale_factor *= 1.25

        self.scale_factor = min(
            self.scale_factor,
            10.0
        )

        self.update_display()

    # ========================================================
    # 缩小
    # ========================================================

    def zoom_out(self):

        if self.original_pixmap is None:
            return

        self.scale_factor /= 1.25

        self.scale_factor = max(
            self.scale_factor,
            0.05
        )

        self.update_display()

    # ========================================================
    # 100%
    # ========================================================

    def zoom_100(self):

        if self.original_pixmap is None:
            return

        self.scale_factor = 1.0

        self.update_display()

    # ========================================================
    # 设置指定缩放值
    # ========================================================

    def set_scale(self, scale):

        if self.original_pixmap is None:
            return

        self.scale_factor = max(
            0.05,
            min(scale, 10.0)
        )

        self.update_display()

    # ========================================================
    # 显示坐标 → 原图坐标
    # ========================================================

    def display_to_image(self, point):

        if self.image is None:
            return 0, 0

        x = int(
            point.x() / self.scale_factor
        )

        y = int(
            point.y() / self.scale_factor
        )

        h, w = self.image.shape[:2]

        x = max(
            0,
            min(x, w - 1)
        )

        y = max(
            0,
            min(y, h - 1)
        )

        return x, y

    # ========================================================
    # 鼠标按下
    # ========================================================

    def mousePressEvent(self, event):

        if (
            self.image is None or
            event.button() != Qt.MouseButton.LeftButton
        ):
            return

        self.dragging = True

        self.start_point = event.position().toPoint()
        self.current_point = self.start_point

        self.update()

    # ========================================================
    # 鼠标移动
    # ========================================================

    def mouseMoveEvent(self, event):

        if self.image is None:
            return

        point = event.position().toPoint()

        x, y = self.display_to_image(point)

        self.mousePixelChanged.emit(
            x,
            y
        )

        if self.dragging:

            self.current_point = point

            self.update()

    # ========================================================
    # 鼠标释放
    # ========================================================

    def mouseReleaseEvent(self, event):

        if (
            not self.dragging or
            self.image is None
        ):
            return

        self.dragging = False

        self.current_point = (
            event.position().toPoint()
        )

        x1, y1 = self.display_to_image(
            self.start_point
        )

        x2, y2 = self.display_to_image(
            self.current_point
        )

        x = min(x1, x2)
        y = min(y1, y2)

        width = abs(x2 - x1) + 1
        height = abs(y2 - y1) + 1

        image_h, image_w = (
            self.image.shape[:2]
        )

        width = min(
            width,
            image_w - x
        )

        height = min(
            height,
            image_h - y
        )

        if width <= 1 or height <= 1:
            return

        self.roi = (
            x,
            y,
            width,
            height
        )

        self.roiChanged.emit(
            x,
            y,
            width,
            height
        )

        self.update()

    # ========================================================
    # 鼠标滚轮缩放
    # ========================================================

    def wheelEvent(self, event):

        if self.image is None:
            return

        if event.angleDelta().y() > 0:

            self.zoom_in()

        else:

            self.zoom_out()

    # ========================================================
    # 绘制ROI
    # ========================================================

    def paintEvent(self, event):

        super().paintEvent(event)

        painter = QPainter(self)

        # 正式ROI
        if self.roi is not None:

            x, y, w, h = self.roi

            draw_x = int(
                x * self.scale_factor
            )

            draw_y = int(
                y * self.scale_factor
            )

            draw_w = int(
                w * self.scale_factor
            )

            draw_h = int(
                h * self.scale_factor
            )

            pen = QPen(
                QColor("#FFD54A"),
                2
            )

            painter.setPen(pen)

            painter.drawRect(
                draw_x,
                draw_y,
                draw_w,
                draw_h
            )

            # ROI文字
            painter.setPen(
                QColor("#FFD54A")
            )

            painter.drawText(
                draw_x + 6,
                max(draw_y - 6, 16),
                f"ROI {w} × {h}"
            )

        # 正在框选
        if (
            self.dragging and
            self.start_point is not None and
            self.current_point is not None
        ):

            x1 = self.start_point.x()
            y1 = self.start_point.y()

            x2 = self.current_point.x()
            y2 = self.current_point.y()

            x = min(x1, x2)
            y = min(y1, y2)

            w = abs(x2 - x1)
            h = abs(y2 - y1)

            pen = QPen(
                QColor("#00E5FF"),
                1,
                Qt.PenStyle.DashLine
            )

            painter.setPen(pen)

            painter.drawRect(
                x,
                y,
                w,
                h
            )


# ============================================================
# 数据显示卡片
# ============================================================

class ValueCard(QFrame):

    def __init__(
        self,
        title,
        unit=""
    ):
        super().__init__()

        self.unit = unit

        self.setObjectName(
            "ValueCard"
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            14,
            10,
            14,
            10
        )

        self.title_label = QLabel(
            title
        )

        self.title_label.setObjectName(
            "CardTitle"
        )

        self.value_label = QLabel(
            "--"
        )

        self.value_label.setObjectName(
            "CardValue"
        )

        layout.addWidget(
            self.title_label
        )

        layout.addWidget(
            self.value_label
        )

    def set_value(self, value):

        if value is None:

            self.value_label.setText(
                "--"
            )

        elif self.unit:

            self.value_label.setText(
                f"{value} {self.unit}"
            )

        else:

            self.value_label.setText(
                str(value)
            )


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Brightness Data Analyzer "
            "图像亮度数据分析系统"
        )

        self.resize(
            1550,
            950
        )

        # 原始图片
        self.image = None

        # 真实亮度数据
        self.brightness_data = None

        # 均值滤波归一化后的修正数据
        self.corrected_data = None

        # 当前ROI数据
        self.roi_data = None
        self.corrected_roi_data = None

        self.image_path = None
        self.data_path = None

        self.create_ui()

        self.apply_style()

    # ========================================================
    # UI
    # ========================================================

    def create_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        main_layout = QVBoxLayout(
            central
        )

        main_layout.setContentsMargins(
            14,
            14,
            14,
            14
        )

        main_layout.setSpacing(10)

        # ====================================================
        # 标题
        # ====================================================

        header_layout = QHBoxLayout()

        title_layout = QVBoxLayout()

        title = QLabel(
            "Brightness Data Analyzer"
        )

        title.setObjectName(
            "MainTitle"
        )

        subtitle = QLabel(
            "图像 / 对应亮度数据 / ROI分析"
        )

        subtitle.setObjectName(
            "SubTitle"
        )

        title_layout.addWidget(
            title
        )

        title_layout.addWidget(
            subtitle
        )

        header_layout.addLayout(
            title_layout
        )

        header_layout.addStretch()

        self.status_label = QLabel(
            "● 等待导入数据"
        )

        self.status_label.setObjectName(
            "StatusLabel"
        )

        header_layout.addWidget(
            self.status_label
        )

        main_layout.addLayout(
            header_layout
        )

        # ====================================================
        # 工具栏
        # ====================================================

        toolbar = QHBoxLayout()

        self.btn_open_image = QPushButton(
            "打开图片"
        )

        self.btn_open_data = QPushButton(
            "导入亮度数据"
        )

        self.btn_zoom_out = QPushButton(
            "－"
        )

        self.btn_zoom_100 = QPushButton(
            "100%"
        )

        self.btn_zoom_in = QPushButton(
            "＋"
        )

        self.btn_analysis = QPushButton(
            "分析 ROI"
        )

        self.btn_save = QPushButton(
            "保存 ROI 数据"
        )

        toolbar.addWidget(
            self.btn_open_image
        )

        toolbar.addWidget(
            self.btn_open_data
        )

        toolbar.addSpacing(20)

        toolbar.addWidget(
            QLabel("缩放")
        )

        toolbar.addWidget(
            self.btn_zoom_out
        )

        toolbar.addWidget(
            self.btn_zoom_100
        )

        toolbar.addWidget(
            self.btn_zoom_in
        )

        toolbar.addSpacing(20)

        toolbar.addWidget(
            self.btn_analysis
        )

        toolbar.addWidget(
            self.btn_save
        )

        toolbar.addStretch()

        self.zoom_label = QLabel(
            "100%"
        )

        toolbar.addWidget(
            self.zoom_label
        )

        main_layout.addLayout(
            toolbar
        )

        # ====================================================
        # 中间区域
        # ====================================================

        center_layout = QHBoxLayout()

        # 图片区域

        image_box = QGroupBox(
            "原始图片 / 鼠标拖动选择 ROI"
        )

        image_layout = QVBoxLayout(
            image_box
        )

        self.viewer = ImageViewer()

        self.scroll_area = QScrollArea()

        self.scroll_area.setWidget(
            self.viewer
        )

        self.scroll_area.setWidgetResizable(
            False
        )

        self.scroll_area.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        image_layout.addWidget(
            self.scroll_area
        )

        # 鼠标信息
        self.mouse_label = QLabel(
            "Pixel: X = --   Y = --   Brightness = --"
        )

        self.mouse_label.setObjectName(
            "InfoLabel"
        )

        image_layout.addWidget(
            self.mouse_label
        )

        center_layout.addWidget(
            image_box,
            4
        )

        # ====================================================
        # 右侧信息
        # ====================================================

        right_panel = QWidget()

        right_layout = QVBoxLayout(
            right_panel
        )

        right_layout.setContentsMargins(
            0,
            0,
            0,
            0
        )

        # 文件信息
        file_group = QGroupBox(
            "数据状态"
        )

        file_layout = QVBoxLayout(
            file_group
        )

        self.image_info_label = QLabel(
            "图片：未导入"
        )

        self.data_info_label = QLabel(
            "亮度数据：未导入"
        )

        self.corrected_info_label = QLabel(
            "修正数据：未关联"
        )

        file_layout.addWidget(
            self.image_info_label
        )

        file_layout.addWidget(
            self.data_info_label
        )

        file_layout.addWidget(
            self.corrected_info_label
        )

        right_layout.addWidget(
            file_group
        )

        # ROI信息

        roi_group = QGroupBox(
            "ROI 信息"
        )

        roi_layout = QGridLayout(
            roi_group
        )

        self.label_x = QLabel("--")
        self.label_y = QLabel("--")
        self.label_w = QLabel("--")
        self.label_h = QLabel("--")

        roi_layout.addWidget(
            QLabel("X："),
            0,
            0
        )

        roi_layout.addWidget(
            self.label_x,
            0,
            1
        )

        roi_layout.addWidget(
            QLabel("Y："),
            1,
            0
        )

        roi_layout.addWidget(
            self.label_y,
            1,
            1
        )

        roi_layout.addWidget(
            QLabel("宽度："),
            2,
            0
        )

        roi_layout.addWidget(
            self.label_w,
            2,
            1
        )

        roi_layout.addWidget(
            QLabel("高度："),
            3,
            0
        )

        roi_layout.addWidget(
            self.label_h,
            3,
            1
        )

        right_layout.addWidget(
            roi_group
        )

        # 数据值卡片

        self.card_mean = ValueCard(
            "原始平均亮度"
        )

        self.card_max = ValueCard(
            "原始最大亮度"
        )

        self.card_min = ValueCard(
            "原始最小亮度"
        )

        self.card_std = ValueCard(
            "原始标准差"
        )

        self.card_contrast = ValueCard("原始散斑对比度")
        self.card_corrected_mean = ValueCard("修正平均亮度")
        self.card_corrected_max = ValueCard("修正最大亮度")
        self.card_corrected_min = ValueCard("修正最小亮度")
        self.card_corrected_std = ValueCard("修正标准差")
        self.card_corrected_contrast = ValueCard("修正散斑对比度")

        stats_layout = QHBoxLayout()
        original_stats = QVBoxLayout()
        corrected_stats = QVBoxLayout()
        for card in (
            self.card_mean, self.card_max, self.card_min,
            self.card_std, self.card_contrast
        ):
            original_stats.addWidget(card)
        for card in (
            self.card_corrected_mean, self.card_corrected_max,
            self.card_corrected_min, self.card_corrected_std,
            self.card_corrected_contrast
        ):
            corrected_stats.addWidget(card)
        stats_layout.addLayout(original_stats)
        stats_layout.addLayout(corrected_stats)
        right_layout.addLayout(stats_layout)

        right_layout.addStretch()

        center_layout.addWidget(
            right_panel,
            2
        )

        main_layout.addLayout(
            center_layout,
            3
        )

        # ====================================================
        # 下方亮度曲线
        # ====================================================

        plot_group = QGroupBox(
            "ROI 亮度分布"
        )

        plot_layout = QVBoxLayout(
            plot_group
        )

        control_layout = QHBoxLayout()

        self.check_horizontal = QCheckBox(
            "横向亮度"
        )

        self.check_horizontal.setChecked(
            True
        )

        self.check_vertical = QCheckBox(
            "纵向亮度"
        )

        self.check_vertical.setChecked(
            False
        )

        control_layout.addWidget(
            self.check_horizontal
        )

        control_layout.addWidget(
            self.check_vertical
        )

        control_layout.addStretch()

        plot_layout.addLayout(
            control_layout
        )

        charts_layout = QHBoxLayout()
        self.plot_widget = pg.PlotWidget(title="原始亮度数据")
        self.corrected_plot_widget = pg.PlotWidget(title="修正亮度数据")
        for widget in (self.plot_widget, self.corrected_plot_widget):
            widget.setBackground("#11161D")
            widget.showGrid(x=True, y=True, alpha=0.25)
            widget.setLabel("bottom", "ROI Pixel")
            widget.setLabel("left", "Brightness")
            widget.addLegend()
            charts_layout.addWidget(widget)
        plot_layout.addLayout(charts_layout)

        main_layout.addWidget(
            plot_group,
            2
        )

        # ====================================================
        # 信号
        # ====================================================

        self.btn_open_image.clicked.connect(
            self.open_image
        )

        self.btn_open_data.clicked.connect(
            self.open_data
        )

        self.btn_zoom_out.clicked.connect(
            self.zoom_out
        )

        self.btn_zoom_100.clicked.connect(
            self.zoom_100
        )

        self.btn_zoom_in.clicked.connect(
            self.zoom_in
        )

        self.btn_analysis.clicked.connect(
            self.analyze_roi
        )

        self.btn_save.clicked.connect(
            self.save_roi
        )

        self.viewer.roiChanged.connect(
            self.roi_changed
        )

        self.viewer.mousePixelChanged.connect(
            self.mouse_pixel_changed
        )

        self.check_horizontal.stateChanged.connect(
            self.draw_brightness_curve
        )

        self.check_vertical.stateChanged.connect(
            self.draw_brightness_curve
        )

    # ========================================================
    # 打开图片
    # ========================================================

    def open_image(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )

        if not path:
            return

        try:

            with Image.open(path) as source_image:

                image = np.asarray(
                    source_image.convert("RGB")
                ).copy()

            self.image = image

            self.image_path = path

            self.viewer.load_image(
                image
            )

            h, w = image.shape[:2]

            self.image_info_label.setText(
                f"图片：{os.path.basename(path)}\n"
                f"尺寸：{w} × {h} Pixel"
            )

            self.status_label.setText(
                "● 图片已导入"
            )

            # 自动关联同目录、同文件名的亮度二进制数据。
            associated_bin = os.path.splitext(path)[0] + ".bin"
            corrected_txt = os.path.join(
                os.path.dirname(path),
                "修正" + os.path.splitext(os.path.basename(path))[0] + ".txt"
            )

            self.brightness_data = None
            self.corrected_data = None
            self.data_path = None
            self.corrected_info_label.setText("修正数据：未关联")

            if os.path.isfile(associated_bin):

                validate_brightness_bin(associated_bin)

                self.brightness_data = np.fromfile(
                    associated_bin,
                    dtype="<f4"
                ).reshape(
                    BRIGHTNESS_HEIGHT,
                    BRIGHTNESS_WIDTH
                )

                self.data_path = associated_bin

                rows, cols = self.brightness_data.shape

                self.data_info_label.setText(
                    f"亮度数据：{os.path.basename(associated_bin)}（自动关联）\n"
                    f"尺寸：{cols} × {rows}"
                )

            if os.path.isfile(corrected_txt):

                self.corrected_data = np.loadtxt(
                    corrected_txt,
                    dtype=np.float32
                )

                rows, cols = self.corrected_data.shape

                self.corrected_info_label.setText(
                    f"修正数据：{os.path.basename(corrected_txt)}（自动关联）\n"
                    f"尺寸：{cols} × {rows}"
                )

            self.update_size_status()

        except Exception as e:

            QMessageBox.critical(
                self,
                "错误",
                str(e)
            )

    # ========================================================
    # 读取亮度数据
    # ========================================================

    def open_data(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择亮度数据",
            "",
            (
                "Data (*.bin *.xlsx *.xls *.csv *.txt *.npy);;"
                "Binary float32 (*.bin);;"
                "Excel (*.xlsx *.xls);;"
                "CSV (*.csv);;"
                "Text (*.txt);;"
                "NumPy (*.npy)"
            )
        )

        if not path:
            return

        try:

            ext = os.path.splitext(
                path
            )[1].lower()

            if ext == ".bin":

                validate_brightness_bin(path)

                data = np.fromfile(
                    path,
                    dtype="<f4"
                ).reshape(
                    BRIGHTNESS_HEIGHT,
                    BRIGHTNESS_WIDTH
                )

            elif ext in (
                ".xlsx",
                ".xls"
            ):

                data = pd.read_excel(
                    path,
                    header=None
                ).to_numpy()

            elif ext == ".csv":

                data = pd.read_csv(
                    path,
                    header=None
                ).to_numpy()

            elif ext == ".txt":

                # 自动尝试空格数据
                try:

                    data = np.loadtxt(
                        path
                    )

                except Exception:

                    # 再尝试逗号
                    data = np.loadtxt(
                        path,
                        delimiter=","
                    )

            elif ext == ".npy":

                data = np.load(
                    path
                )

            else:

                raise ValueError(
                    "不支持的数据格式"
                )

            # 必须二维
            if data.ndim != 2:

                raise ValueError(
                    "亮度数据必须为二维矩阵"
                )

            # 转浮点
            data = data.astype(
                np.float64
            )

            self.brightness_data = data

            self.data_path = path

            rows, cols = data.shape

            self.data_info_label.setText(
                f"亮度数据：{os.path.basename(path)}\n"
                f"尺寸：{cols} × {rows}"
            )

            self.update_size_status()

        except Exception as e:

            QMessageBox.critical(
                self,
                "数据读取失败",
                str(e)
            )

    # ========================================================
    # 检查图片和数据尺寸
    # ========================================================

    def update_size_status(self):

        if (
            self.image is None or
            self.brightness_data is None
        ):
            return

        image_h, image_w = (
            self.image.shape[:2]
        )

        data_h, data_w = (
            self.brightness_data.shape
        )

        if (
            image_w == data_w and
            image_h == data_h
        ):

            self.status_label.setText(
                "● 图片与亮度数据尺寸匹配"
            )

            self.status_label.setStyleSheet(
                "color:#43D17A;"
            )

        else:

            self.status_label.setText(
                "● 图片与数据尺寸不匹配"
            )

            self.status_label.setStyleSheet(
                "color:#FF5D73;"
            )

            QMessageBox.warning(
                self,
                "尺寸不匹配",
                (
                    f"图片尺寸："
                    f"{image_w} × {image_h}\n\n"
                    f"数据尺寸："
                    f"{data_w} × {data_h}\n\n"
                    "亮度数据必须和图片像素完全对应。"
                )
            )

    # ========================================================
    # ROI改变
    # ========================================================

    def roi_changed(
        self,
        x,
        y,
        w,
        h
    ):

        self.label_x.setText(
            str(x)
        )

        self.label_y.setText(
            str(y)
        )

        self.label_w.setText(
            str(w)
        )

        self.label_h.setText(
            str(h)
        )

        # 有数据就直接分析
        if self.brightness_data is not None:

            self.analyze_roi()

    # ========================================================
    # ROI分析
    # ========================================================

    def analyze_roi(self):

        if self.image is None:

            QMessageBox.warning(
                self,
                "提示",
                "请先导入图片"
            )

            return

        if self.brightness_data is None:

            QMessageBox.warning(
                self,
                "提示",
                "请先导入对应的亮度数据"
            )

            return

        if self.viewer.roi is None:

            QMessageBox.warning(
                self,
                "提示",
                "请先在图片上框选区域"
            )

            return

        image_h, image_w = (
            self.image.shape[:2]
        )

        data_h, data_w = (
            self.brightness_data.shape
        )

        if (
            image_w != data_w or
            image_h != data_h
        ):

            QMessageBox.warning(
                self,
                "错误",
                "图片尺寸和亮度数据尺寸不同"
            )

            return

        x, y, w, h = (
            self.viewer.roi
        )

        self.roi_data = (
            self.brightness_data[
                y:y + h,
                x:x + w
            ]
        )

        self.corrected_roi_data = None
        if self.corrected_data is not None:
            if self.corrected_data.shape != self.brightness_data.shape:
                QMessageBox.warning(self, "错误", "修正数据和原始亮度数据尺寸不同")
                return
            self.corrected_roi_data = self.corrected_data[y:y + h, x:x + w]

        if self.roi_data.size == 0:

            return

        mean_value = np.mean(
            self.roi_data
        )

        max_value = np.max(
            self.roi_data
        )

        min_value = np.min(
            self.roi_data
        )

        std_value = np.std(
            self.roi_data
        )

        self.card_mean.set_value(
            f"{mean_value:.6f}"
        )

        self.card_max.set_value(
            f"{max_value:.6f}"
        )

        self.card_min.set_value(
            f"{min_value:.6f}"
        )

        self.card_std.set_value(
            f"{std_value:.6f}"
        )

        original_contrast = std_value / mean_value if mean_value != 0 else 0.0
        self.card_contrast.set_value(f"{original_contrast:.6f}")

        if self.corrected_roi_data is not None and self.corrected_roi_data.size:
            corrected_mean = np.mean(self.corrected_roi_data)
            corrected_max = np.max(self.corrected_roi_data)
            corrected_min = np.min(self.corrected_roi_data)
            corrected_std = np.std(self.corrected_roi_data)
            corrected_contrast = (
                corrected_std / corrected_mean if corrected_mean != 0 else 0.0
            )
            self.card_corrected_mean.set_value(f"{corrected_mean:.6f}")
            self.card_corrected_max.set_value(f"{corrected_max:.6f}")
            self.card_corrected_min.set_value(f"{corrected_min:.6f}")
            self.card_corrected_std.set_value(f"{corrected_std:.6f}")
            self.card_corrected_contrast.set_value(f"{corrected_contrast:.6f}")

        self.draw_brightness_curve()

    # ========================================================
    # 绘制亮度曲线
    # ========================================================

    def draw_brightness_curve(self):

        if self.roi_data is None:
            return

        self.plot_widget.clear()
        self.corrected_plot_widget.clear()

        # 横向
        # 每一列所有Y值求平均
        if self.check_horizontal.isChecked():

            horizontal_curve = np.mean(
                self.roi_data,
                axis=0
            )

            self.plot_widget.plot(
                horizontal_curve,
                pen=pg.mkPen(
                    "#FFD54A",
                    width=2
                ),
                name="Horizontal"
            )

            if self.corrected_roi_data is not None:
                corrected_horizontal = np.mean(self.corrected_roi_data, axis=0)
                self.corrected_plot_widget.plot(
                    corrected_horizontal,
                    pen=pg.mkPen("#FFD54A", width=2),
                    name="Horizontal"
                )

        # 纵向
        # 每一行所有X值求平均
        if self.check_vertical.isChecked():

            vertical_curve = np.mean(
                self.roi_data,
                axis=1
            )

            self.plot_widget.plot(
                vertical_curve,
                pen=pg.mkPen(
                    "#00D4FF",
                    width=2
                ),
                name="Vertical"
            )

            if self.corrected_roi_data is not None:
                corrected_vertical = np.mean(self.corrected_roi_data, axis=1)
                self.corrected_plot_widget.plot(
                    corrected_vertical,
                    pen=pg.mkPen("#00D4FF", width=2),
                    name="Vertical"
                )

    # ========================================================
    # 鼠标像素显示
    # ========================================================

    def mouse_pixel_changed(
        self,
        x,
        y
    ):

        brightness_text = "--"
        corrected_text = "--"

        if self.brightness_data is not None:

            h, w = (
                self.brightness_data.shape
            )

            if (
                0 <= x < w and
                0 <= y < h
            ):

                value = (
                    self.brightness_data[
                        y,
                        x
                    ]
                )

                brightness_text = (
                    f"{value:.6f}"
                )

                if self.corrected_data is not None:
                    corrected_text = f"{self.corrected_data[y, x]:.6f}"

        self.mouse_label.setText(
            f"Pixel: X = {x}    "
            f"Y = {y}    "
            f"Brightness = {brightness_text}    "
            f"Corrected = {corrected_text}"
        )

    # ========================================================
    # 缩放
    # ========================================================

    def zoom_in(self):

        self.viewer.zoom_in()

        self.update_zoom_label()

    def zoom_out(self):

        self.viewer.zoom_out()

        self.update_zoom_label()

    def zoom_100(self):

        self.viewer.zoom_100()

        self.update_zoom_label()

    def update_zoom_label(self):

        self.zoom_label.setText(
            f"{self.viewer.scale_factor * 100:.0f}%"
        )

    # ========================================================
    # 保存ROI
    # ========================================================

    def save_roi(self):

        if self.roi_data is None:

            QMessageBox.warning(
                self,
                "提示",
                "当前没有ROI亮度数据"
            )

            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存 ROI 数据",
            "brightness_roi.xlsx",
            "Excel (*.xlsx)"
        )

        if not path:
            return

        if not path.lower().endswith(
            ".xlsx"
        ):

            path += ".xlsx"

        x, y, w, h = (
            self.viewer.roi
        )

        horizontal_curve = np.mean(
            self.roi_data,
            axis=0
        )

        vertical_curve = np.mean(
            self.roi_data,
            axis=1
        )

        stats = pd.DataFrame({
            "参数": [
                "X",
                "Y",
                "Width",
                "Height",
                "Mean",
                "Max",
                "Min",
                "STD"
            ],
            "数值": [
                x,
                y,
                w,
                h,
                np.mean(
                    self.roi_data
                ),
                np.max(
                    self.roi_data
                ),
                np.min(
                    self.roi_data
                ),
                np.std(
                    self.roi_data
                )
            ]
        })

        with pd.ExcelWriter(
            path,
            engine="openpyxl"
        ) as writer:

            stats.to_excel(
                writer,
                sheet_name="Statistics",
                index=False
            )

            pd.DataFrame(
                self.roi_data
            ).to_excel(
                writer,
                sheet_name="ROI_Data",
                index=False,
                header=False
            )

            pd.DataFrame({
                "X": np.arange(
                    len(horizontal_curve)
                ),
                "Brightness": (
                    horizontal_curve
                )
            }).to_excel(
                writer,
                sheet_name="Horizontal",
                index=False
            )

            pd.DataFrame({
                "Y": np.arange(
                    len(vertical_curve)
                ),
                "Brightness": (
                    vertical_curve
                )
            }).to_excel(
                writer,
                sheet_name="Vertical",
                index=False
            )

        QMessageBox.information(
            self,
            "完成",
            "ROI亮度数据保存成功"
        )

    # ========================================================
    # 样式
    # ========================================================

    def apply_style(self):

        self.setStyleSheet("""
            QMainWindow {
                background: #151A21;
            }

            QWidget {
                color: #D9E1EA;
                font-family: "Microsoft YaHei";
                font-size: 13px;
            }

            #MainTitle {
                font-size: 22px;
                font-weight: 600;
                color: #F2F6FA;
            }

            #SubTitle {
                color: #7F8B99;
                font-size: 12px;
            }

            #StatusLabel {
                color: #9DA8B5;
                font-size: 13px;
            }

            #InfoLabel {
                background: #10151B;
                border: 1px solid #2A333D;
                padding: 7px;
                color: #AEB9C6;
            }

            QPushButton {
                background: #252D37;
                border: 1px solid #36414E;
                border-radius: 5px;
                padding: 7px 14px;
                min-height: 22px;
            }

            QPushButton:hover {
                background: #303A46;
                border: 1px solid #4A95D1;
            }

            QPushButton:pressed {
                background: #1E252D;
            }

            QGroupBox {
                border: 1px solid #2E3742;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: 600;
                color: #C9D2DD;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
            }

            QScrollArea {
                border: 1px solid #2A333D;
                background: #0F1318;
            }

            #ValueCard {
                background: #1B222B;
                border: 1px solid #303A46;
                border-radius: 6px;
            }

            #CardTitle {
                color: #8795A5;
                font-size: 12px;
            }

            #CardValue {
                color: #FFFFFF;
                font-size: 21px;
                font-weight: 600;
            }

            QCheckBox {
                spacing: 7px;
            }
        """)


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":

    if len(sys.argv) >= 3 and sys.argv[1] == "--convert":

        source_path = sys.argv[2]

        destination_path = (
            sys.argv[3]
            if len(sys.argv) >= 4
            else None
        )

        output_path = convert_brightness_bin_to_txt(
            source_path,
            destination_path
        )

        print(
            f"亮度TXT已保存：{output_path}"
        )

        raise SystemExit(0)

    app = QApplication(
        sys.argv
    )

    pg.setConfigOptions(
        antialias=True
    )

    window = MainWindow()

    window.show()

    sys.exit(
        app.exec()
    )
