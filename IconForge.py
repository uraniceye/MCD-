#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCD图标工具 (IconForge Pro) V4.0 - 专业图标批量生成与处理套件
作者：跳舞的火公子
功能：批量处理、预设系统、撤销/重做、高级图像调整 (颜色叠加)、平台化输出模板。
"""

# ==============================================================================
# SECTION 0: 核心依赖导入
# ==============================================================================
import sys
import os
import json
import re       # [新增] 用于处理 SVG 文件内容的正则表达式
import shutil   # [新增] 用于文件复制
import zipfile  # [新增] 用于处理 ZIP 压缩文件
from io import BytesIO
from typing import List, Tuple, Optional, Dict, Any

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QPushButton, QLabel, QLineEdit, QCheckBox, QFrame, QFileDialog,
    QMessageBox, QGroupBox, QStatusBar, QSlider, QColorDialog, QRadioButton,
    QButtonGroup, QDockWidget, QTabWidget, QListWidget, QListWidgetItem,
    QAbstractItemView, QProgressDialog, QUndoStack, QUndoView, QUndoCommand,
    QToolBar, QSizePolicy, QStackedWidget
)
from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QIcon, QBrush
from PyQt5.QtSvg import QSvgRenderer  # [核心修正] QSvgRenderer 属于 QtSvg 模块
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QRunnable, QObject, QThreadPool, QBuffer

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
    PILLOW_AVAILABLE = True
except ImportError:
    # Pillow是核心依赖，没有它程序无法运行
    print("严重错误: Pillow (PIL) 库未找到。程序无法运行。请运行: pip install Pillow")
    sys.exit(1)

try:
    import requests  # [新增] 用于下载图标库文件
except ImportError:
    # requests 是自动下载功能的核心依赖，但我们可以让程序在没有它的情况下也能运行，只是功能降级
    print("警告: requests 库未找到。'图标库自动下载'功能将被禁用。若要启用，请运行: pip install requests")
    # 为了防止程序崩溃，我们可以在后面创建一个假的 requests 对象或在调用处检查
    # 但更简单的做法是让依赖明确，如果需要自动下载，就必须安装。
    # 这里我们选择让程序继续运行，并在需要下载时再处理错误。
    pass

# --- [核心修正] 移除顶层的 rembg 导入，改为在主窗口中异步加载 ---
# 默认情况下，rembg 功能是不可用的，直到后台初始化成功。
REMBG_AVAILABLE = False

# ==============================================================================
# SECTION 1: 数据模型与核心逻辑 (MODELS & CORE LOGIC)
# ==============================================================================

class IconGenerator:
    """
    核心图标生成器 (V4.0)，支持更复杂的处理链和批量操作。
    [已修正] 支持 SVG 源文件输入、rembg 异步加载和独立的单尺寸ICO文件生成。
    """
    
    def process_image(self, source_img: Image.Image, options: Dict[str, Any], remove_func: Optional[callable] = None) -> Image.Image:
        """
        [已重写] 根据指定的选项，对源图像进行一系列处理，包含高级效果。
        处理顺序: 校正 -> 基础处理 -> 特效 -> 水印 -> 最终裁剪/塑形
        """
        img = source_img.copy().convert("RGBA")

        # --- 阶段 1: 图像校正 ---
        brightness = 1.0 + (options.get('adv_brightness', 0) / 100.0)
        contrast = 1.0 + (options.get('adv_contrast', 0) / 100.0)
        saturation = 1.0 + (options.get('adv_saturation', 0) / 100.0)

        if brightness != 1.0: img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0: img = ImageEnhance.Contrast(img).enhance(contrast)
        if saturation != 1.0: img = ImageEnhance.Color(img).enhance(saturation)

        # --- 阶段 2: 核心处理 (背景和颜色) ---
        if options.get('remove_bg') and REMBG_AVAILABLE and remove_func:
            try: img = remove_func(img)
            except Exception as e: print(f"背景移除失败: {e}")
        
        if options.get('bg_color'):
            background = Image.new("RGBA", img.size, options['bg_color'])
            background.paste(img, (0, 0), img)
            img = background
        
        if options.get('color_overlay_enabled'):
            overlay_color = options.get('color_overlay', '#ffffff')
            overlay = Image.new("RGBA", img.size, overlay_color)
            alpha = img.getchannel('A')
            img.paste(overlay, (0,0), alpha)

        # --- 阶段 3: 阴影与描边 ---
        if options.get('adv_fx_enabled'):
            alpha = img.getchannel('A')
            
            if options.get('adv_fx_mode') == 'shadow':
                blur = options.get('adv_shadow_blur', 5)
                offset_x = options.get('adv_shadow_offset_x', 5)
                offset_y = options.get('adv_shadow_offset_y', 5)
                color = options.get('adv_shadow_color', '#000000')

                shadow = Image.new('RGBA', img.size, color)
                shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(blur))
                
                fx_canvas = Image.new('RGBA', (img.width + abs(offset_x) + blur*2, img.height + abs(offset_y) + blur*2), (0,0,0,0))
                shadow_paste_pos = (blur + (offset_x if offset_x > 0 else 0), blur + (offset_y if offset_y > 0 else 0))
                fx_canvas.paste(shadow, shadow_paste_pos, shadow_alpha)
                img_paste_pos = (blur - (offset_x if offset_x < 0 else 0), blur - (offset_y if offset_y < 0 else 0))
                fx_canvas.paste(img, img_paste_pos, img)
                img = fx_canvas

            elif options.get('adv_fx_mode') == 'stroke':
                width = options.get('adv_stroke_width', 2)
                color = options.get('adv_stroke_color', '#ffffff')

                stroke_alpha = alpha
                for _ in range(width):
                    stroke_alpha = stroke_alpha.filter(ImageFilter.MaxFilter(3))
                
                stroke = Image.new('RGBA', img.size, color)
                
                fx_canvas = Image.new('RGBA', img.size, (0,0,0,0))
                fx_canvas.paste(stroke, (0,0), stroke_alpha)
                fx_canvas.paste(img, (0,0), img)
                img = fx_canvas

        # --- 阶段 4: 尺寸与内边距 ---
        padding = options.get('padding', 0)
        if padding > 0:
            target_size_inner = max(img.width, img.height)
            new_size = int(target_size_inner / (1 - (padding / 100)))
            padded_img = Image.new("RGBA", (new_size, new_size), (0, 0, 0, 0))
            paste_pos = ((new_size - img.width) // 2, (new_size - img.height) // 2)
            padded_img.paste(img, paste_pos, img)
            img = padded_img

        # --- 阶段 5: 水印 ---
        if options.get('adv_watermark_enabled') and options.get('adv_watermark_path'):
            watermark_path = options.get('adv_watermark_path')
            if os.path.exists(watermark_path):
                try:
                    watermark = Image.open(watermark_path).convert("RGBA")
                    
                    wm_size_perc = options.get('adv_watermark_size', 20) / 100.0
                    base_size = min(img.width, img.height)
                    new_wm_width = int(base_size * wm_size_perc)
                    wm_ratio = watermark.height / watermark.width
                    new_wm_height = int(new_wm_width * wm_ratio)
                    watermark = watermark.resize((new_wm_width, new_wm_height), Image.LANCZOS)
                    
                    opacity_perc = options.get('adv_watermark_opacity', 50)
                    if opacity_perc < 100:
                        alpha = watermark.getchannel('A')
                        alpha = ImageEnhance.Brightness(alpha).enhance(opacity_perc / 100.0)
                        watermark.putalpha(alpha)
                    
                    pos_map = {
                        'top_left': (0, 0), 'top_center': ((img.width - new_wm_width)//2, 0), 'top_right': (img.width - new_wm_width, 0),
                        'mid_left': (0, (img.height - new_wm_height)//2), 'center': ((img.width - new_wm_width)//2, (img.height - new_wm_height)//2), 'mid_right': (img.width - new_wm_width, (img.height - new_wm_height)//2),
                        'bottom_left': (0, img.height - new_wm_height), 'bottom_center': ((img.width - new_wm_width)//2, img.height - new_wm_height), 'bottom_right': (img.width - new_wm_width, img.height - new_wm_height)
                    }
                    pos = pos_map.get(options.get('adv_watermark_pos'), 'bottom_right')
                    
                    img.paste(watermark, pos, watermark)
                except Exception as e:
                    print(f"应用水印失败: {e}")

        # --- 阶段 6: 最终塑形 (圆角) ---
        radius_percent = options.get('radius', 0)
        if radius_percent > 0:
            radius = int(min(img.width, img.height) * (radius_percent / 100) / 2)
            if radius > 0:
                mask = Image.new("L", img.size, 0)
                draw = ImageDraw.Draw(mask)
                draw.rounded_rectangle((0, 0) + img.size, radius, fill=255)
                img.putalpha(mask)

        return img


    def _generate_svg(self, source_path: str, output_dir: str, base_name: str, options: Dict[str, Any]):
        """
        [新增] 专门处理 SVG 到 SVG 的生成。
        仅支持颜色叠加，忽略其他所有光栅效果。
        """
        output_file = os.path.join(output_dir, f"{base_name}.svg")
        
        # 如果未启用颜色叠加，直接复制源文件
        if not options.get('color_overlay_enabled'):
            shutil.copy2(source_path, output_file)
            return

        # 如果启用了颜色叠加，读取 SVG 内容并替换颜色
        try:
            with open(source_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()
            
            new_color = options.get('color_overlay', '#000000')
            
            # 使用正则表达式替换 fill 和 stroke 属性中的颜色
            # 这个正则表达式会避免替换 "none" 或 "url(...)"
            svg_content = re.sub(r'fill="(?!(none|url))[^\"]+"', f'fill="{new_color}"', svg_content)
            svg_content = re.sub(r'stroke="(?!(none|url))[^\"]+"', f'stroke="{new_color}"', svg_content)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(svg_content)

        except Exception as e:
            raise IOError(f"处理 SVG 文件 '{os.path.basename(source_path)}' 失败: {e}")
    def generate(self, source_path: str, output_dir: str, base_name: str, options: Dict[str, Any], remove_func: Optional[callable] = None):
        """
        [已重构] 生成图标的主入口点。
        - 支持 SVG 源文件输入。
        - 接收 remove_func 以支持异步加载。
        - ICO格式现在会为每个选定的尺寸生成一个单独的文件。
        - [新增] 增加了对 SVG 输出格式的特殊处理分支。
        """
        fmt = options.get('format', 'ico')
        
        # 确保输出目录存在
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # --- [核心修正] SVG 输出的独立处理路径 ---
        if fmt == 'svg':
            # SVG输出格式仅在源文件也是SVG时有效
            if not source_path.lower().endswith('.svg'):
                raise ValueError("SVG输出格式仅支持SVG源文件。")
            
            # 调用专门的SVG处理方法，该方法仅处理颜色替换
            self._generate_svg(source_path, output_dir, base_name, options)
            return # SVG 处理完毕，直接返回，不执行后续的光栅化操作

        # --- 原有的光栅图像处理路径 (ICO, ICNS, PNG) ---
        # 步骤 1: 将源文件（无论是SVG还是位图）加载为 Pillow Image 对象
        if source_path.lower().endswith('.svg'):
            renderer = QSvgRenderer(source_path)
            # 渲染到一个足够大的 QPixmap (例如 1024x1024) 以保留矢量细节
            pixmap = QPixmap(1024, 1024)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            
            # 将 QPixmap 转换为 Pillow Image 以便后续处理
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            pixmap.save(buffer, "PNG")
            source_img = Image.open(BytesIO(buffer.data()))
        else:
            # 原有的位图文件处理逻辑
            source_img = Image.open(source_path)
        
        # 步骤 2: 对加载好的 Pillow Image 进行所有光栅效果处理
        processed_img = self.process_image(source_img, options, remove_func)
        
        # 步骤 3: 根据目标格式保存处理后的图像
        sizes = options.get('sizes', [])

        if fmt == 'ico':
            if not sizes: raise ValueError("ICO 格式必须至少选择一个尺寸。")
            for size_tuple in sizes:
                size = size_tuple[0]
                resized_img = processed_img.resize((size, size), Image.LANCZOS)
                filename = os.path.join(output_dir, f"{base_name}_{size}x{size}.ico")
                resized_img.save(filename, format='ICO')
        
        elif fmt == 'icns':
            output_file = os.path.join(output_dir, f"{base_name}.icns")
            processed_img.save(output_file, format='ICNS')
            
        elif fmt == 'png_suite':
            if not sizes: raise ValueError("PNG套件必须至少选择一个尺寸。")
            for size_tuple in sizes:
                size = size_tuple[0]
                resized_img = processed_img.resize((size, size), Image.LANCZOS)
                filename = os.path.join(output_dir, f"{base_name}_{size}x{size}.png")
                resized_img.save(filename, format='PNG')
        else:
            # 如果程序执行到这里，说明是一个未知的非SVG格式
            raise ValueError(f"不支持的输出格式: {fmt}")


class GenerateWorker(QRunnable):
    """
    [已修正] 在后台线程中执行批量生成任务。
    现在会接收并传递 remove_func 以支持异步加载的 rembg。
    """
    class Signals(QObject):
        progress = pyqtSignal(int, int, str)
        finished = pyqtSignal(str)
        error = pyqtSignal(str)

    def __init__(self, generator: IconGenerator, batch: List[str], output_path: str, options: Dict[str, Any], remove_func: Optional[callable]):
        super().__init__()
        self.signals = self.Signals()
        self.generator = generator
        self.batch = batch
        self.output_path = output_path
        self.options = options
        # [核心修正] 存储从主线程传入的 rembg 的 remove 函数
        self.remove_func = remove_func
        self.is_cancelled = False

    def cancel(self):
        """设置取消标志，以请求中断任务。"""
        self.is_cancelled = True

    def run(self):
        try:
            total = len(self.batch)
            fmt = self.options.get('format')
            is_batch = total > 1
            
            # 采用更健壮的方式来确定输出目录 (output_dir)
            if is_batch or fmt == 'png_suite':
                output_dir = self.output_path
            else:
                output_dir = os.path.dirname(self.output_path)
            
            for i, source_path in enumerate(self.batch):
                if self.is_cancelled:
                    self.signals.finished.emit("操作已取消。")
                    return
                
                base_name = os.path.splitext(os.path.basename(source_path))[0]

                # 如果是单文件 ico/icns，base_name 需要被重写为用户指定的文件名
                if not is_batch and fmt in ['ico', 'icns']:
                    base_name = os.path.splitext(os.path.basename(self.output_path))[0]

                self.signals.progress.emit(i, total, base_name)
                
                # [核心修正] 将存储的 remove_func 传递给 generate 方法
                self.generator.generate(source_path, output_dir, base_name, self.options, self.remove_func)
            
            self.signals.finished.emit(f"成功生成 {total} 个图标批次到:\n{output_dir}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.signals.error.emit(str(e))
class ThumbnailWorker(QRunnable):
    """在后台线程中为列表项生成缩略图。"""
    class Signals(QObject):
        finished = pyqtSignal(QListWidgetItem, QIcon)

    def __init__(self, item: QListWidgetItem, source_path: str, size: QSize):
        super().__init__()
        self.signals = self.Signals()
        self.item = item
        self.source_path = source_path
        self.size = size

    def run(self):
        try:
            # [核心修正] 增加对 SVG 的处理
            if self.source_path.lower().endswith('.svg'):
                # 使用 Qt 的原生 SVG 渲染器
                renderer = QSvgRenderer(self.source_path)
                qimage = QImage(self.size, QImage.Format_ARGB32)
                qimage.fill(Qt.transparent)
                painter = QPainter(qimage)
                renderer.render(painter)
                painter.end() # 必须在 QImage 被使用前结束绘制
                pixmap = QPixmap.fromImage(qimage)
            else:
                # 保持对 PNG/JPG 的原有处理逻辑
                img = Image.open(self.source_path)
                img.thumbnail((self.size.width(), self.size.height()), Image.LANCZOS)
                buffer = BytesIO()
                img.save(buffer, "PNG")
                qimage = QImage.fromData(buffer.getvalue())
                pixmap = QPixmap.fromImage(qimage)
            
            icon = QIcon(pixmap)
            self.signals.finished.emit(self.item, icon)
        except Exception as e:
            print(f"为 {os.path.basename(self.source_path)} 生成缩略图失败: {e}")

class RembgInitializer(QRunnable):
    """在后台线程中安全地初始化rembg库，避免阻塞UI。"""
    class Signals(QObject):
        # 信号：(初始化是否成功, 成功时返回的 remove 函数)
        finished = pyqtSignal(bool, object)

    def __init__(self):
        super().__init__()
        self.signals = self.Signals()

    def run(self):
        """尝试导入 rembg。这可能会触发模型下载。"""
        try:
            from rembg import remove
            # 成功，发射带有 True 和 remove 函数的信号
            self.signals.finished.emit(True, remove)
        except Exception as e:
            print(f"Rembg 初始化失败: {e}")
            # 失败，发射带有 False 和 None 的信号
            self.signals.finished.emit(False, None)

class LibraryScanner(QRunnable):
    """
    [最终修正版] 在后台扫描本地的图标库目录，现在支持 SVG 文件。
    """
    class Signals(QObject):
        finished = pyqtSignal(dict)
        # [核心修正] 恢复 progress 信号，以修复 AttributeError
        progress = pyqtSignal(int, int, str)

    def __init__(self, library_path="icon_library"):
        super().__init__()
        self.signals = self.Signals()
        self.library_path = library_path

    def run(self):
        """直接扫描本地目录并构建索引。"""
        icon_library = {}
        if not os.path.isdir(self.library_path):
            print(f"提示: 图标库目录 '{self.library_path}' 未找到。请根据说明手动创建并填充。")
            self.signals.finished.emit({})
            return

        try:
            # 因为 lucide 的 svg 是扁平结构，我们不再寻找子目录
            self.signals.progress.emit(0, 100, "正在扫描图标库...")
            icons = []
            all_files = os.listdir(self.library_path)
            total_files = len(all_files)
            
            for i, icon_file in enumerate(sorted(all_files)):
                if icon_file.lower().endswith('.svg'):
                    icons.append(os.path.join(self.library_path, icon_file))
                # [核心修正] 在扫描时发射进度信号
                if total_files > 0:
                    progress = int((i + 1) / total_files * 100)
                    self.signals.progress.emit(progress, 100, "正在扫描图标库...")

            if icons:
                icon_library["通用图标"] = icons
            
            self.signals.finished.emit(icon_library)

        except Exception as e:
            print(f"扫描图标库时出错: {e}")
            self.signals.finished.emit({})











# ==============================================================================
# SECTION 2: QT 特定模型与命令 (QT MODELS & COMMANDS)
# ==============================================================================
class ModifyOptionsCommand(QUndoCommand):
    """一个用于记录处理选项修改的 QUndoCommand。"""
    def __init__(self, main_window: 'IconForgeWindow', key: str, new_value: Any, description: str):
        super().__init__(description)
        self.main = main_window
        self.key = key
        self.new_value = new_value
        self.old_value = self.main.current_options[key]

    def redo(self):
        self.main.current_options[self.key] = self.new_value
        self.main._update_ui_from_options()
        self.main._update_realtime_preview()

    def undo(self):
        self.main.current_options[self.key] = self.old_value
        self.main._update_ui_from_options()
        self.main._update_realtime_preview()

# ==============================================================================
# SECTION 3: 主窗口与控制器 (MAIN WINDOW & CONTROLLER)
# ==============================================================================
class Theme:
    """管理应用程序的颜色和全局样式表 (QSS)。"""
    LIGHT = {
        "bg-primary": "#f8fafc", "bg-secondary": "#ffffff", "bg-tertiary": "#f1f5f9",
        "content-primary": "#0f172a", "content-secondary": "#64748b",
        "accent-primary": "#4f46e5", "accent-primary-hover": "#6366f1", "accent-primary-pressed": "#4338ca",
        "border-primary": "#e2e8f0", "danger": "#ef4444", "success": "#22c55e",
        "warning": "#f59e0b", "info": "#3b82f6"
    }
    @staticmethod
    def get_qss() -> str:
        colors = Theme.LIGHT
        return f"""
            QMainWindow, QStatusBar, QDockWidget {{
                background-color: {colors['bg-primary']};
            }}
            QToolBar {{
                background-color: {colors['accent-primary']};
                border: none;
                padding: 0px;
                spacing: 10px;
            }}
            QLabel#NavTitleLabel {{
                color: white;
                font-size: 16pt;
                font-weight: bold;
                padding-left: 10px;
            }}
            QTabWidget::pane {{
                border: none;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {colors['content-secondary']};
                padding: 8px 15px;
                border-bottom: 2px solid transparent;
                font-weight: bold;
            }}
            QTabBar::tab:hover {{
                color: {colors['content-primary']};
            }}
            QTabBar::tab:selected {{
                color: {colors['accent-primary']};
                border-bottom: 2px solid {colors['accent-primary']};
            }}
            QListWidget {{
                background-color: {colors['bg-secondary']};
                border: 1px solid {colors['border-primary']};
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {colors['accent-primary']};
                color: white;
            }}
            QPushButton {{
                border: none;
                padding: 8px 12px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10pt;
            }}
            QPushButton[cssClass="toolbar"] {{
                background-color: {colors['accent-primary-hover']};
                color: white;
                padding: 8px 14px;
            }}
            QPushButton[cssClass="toolbar"]:hover {{
                background-color: {colors['accent-primary-pressed']};
            }}
            QPushButton#PrimaryButton {{
                background-color: {colors['success']};
                color: white;
                font-size: 11pt;
                padding: 12px;
            }}
            QPushButton#PrimaryButton:hover {{
                background-color: #16a34a;
            }}
            QSlider::groove:horizontal {{
                border: 1px solid #bbb;
                background: white;
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {colors['accent-primary']};
                border: 1px solid {colors['accent-primary']};
                width: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }}
            QLineEdit {{
                border: 1px solid {colors['border-primary']};
                border-radius: 4px;
                padding: 5px;
            }}
        """

class CardWidget(QFrame):
    """一个可重用的、带标题的卡片式布局容器。"""
    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme = Theme.LIGHT
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(0)
        
        self.title_bar = QLabel(title)
        self._content_widget = QWidget()
        
        main_layout.addWidget(self.title_bar)
        main_layout.addWidget(self._content_widget, 1)
        
        self.setObjectName("CardWidget")
        self.setStyleSheet(f"""
            #CardWidget {{
                background-color: {self.theme['bg-secondary']};
                border: 1px solid {self.theme['border-primary']};
                border-radius: 6px;
            }}
        """)
        self.title_bar.setStyleSheet(f"""
            QLabel {{
                background-color: {self.theme['bg-tertiary']};
                color: {self.theme['content-primary']};
                padding: 10px 15px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border-bottom: 1px solid {self.theme['border-primary']};
                font-size: 11pt;
                font-weight: bold;
            }}
        """)
    def contentWidget(self) -> QWidget:
        return self._content_widget
class EmptyListWidget(QWidget):
    """
    当列表为空时显示的引导性Widget。
    [已升级] 文件夹图标现在可以点击，并会发射一个信号。
    """
    # 1. 定义一个自定义信号，当图标被点击时发射
    folder_icon_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(15)

        # 2. 将原来的 QLabel 换成 QPushButton
        self.icon_button = QPushButton("📂")
        # 3. 为按钮设置样式，让它看起来像一个无边框的图标，并在悬停时显示手形光标
        self.icon_button.setCursor(Qt.PointingHandCursor)
        self.icon_button.setStyleSheet("""
            QPushButton {
                font-size: 48pt;
                border: none;
                background: transparent;
                padding: 10px;
            }
            QPushButton:hover {
                /* 可以添加一个轻微的背景色来提示可点击 */
                background-color: #f0f0f0;
                border-radius: 8px;
            }
        """)
        
        text_label = QLabel("列表为空")
        text_label.setStyleSheet(f"color: {Theme.LIGHT['content-primary']}; font-size: 14pt; font-weight: bold;")
        
        info_label = QLabel("将文件/文件夹拖拽到此处\n或点击上方图标及顶部工具栏按钮添加")
        info_label.setAlignment(Qt.AlignCenter)
        info_label.setStyleSheet(f"color: {Theme.LIGHT['content-secondary']};")

        # 4. 将按钮的 clicked 信号连接到我们自定义信号的 emit() 方法
        self.icon_button.clicked.connect(self.folder_icon_clicked.emit)

        # 5. 将新的按钮添加到布局中
        layout.addWidget(self.icon_button, alignment=Qt.AlignCenter)
        layout.addWidget(text_label, alignment=Qt.AlignCenter)
        layout.addWidget(info_label, alignment=Qt.AlignCenter)


class IconForgeWindow(QMainWindow):
    """应用程序的主窗口 V4.0。"""
    
    PLATFORM_TEMPLATES = {
        "Windows (.ico)": {'sizes': [16, 24, 32, 48, 256], 'format': 'ico'},
        "macOS (.icns)": {'sizes': [], 'format': 'icns'},
        "Android Adaptive": {'sizes': [48, 72, 96, 144, 192, 512], 'format': 'png_suite'},
        "iOS AppIcon": {'sizes': [20, 29, 40, 58, 60, 76, 80, 87, 120, 152, 167, 180, 1024], 'format': 'png_suite'},
        "Vector (.svg)": {'sizes': [], 'format': 'svg'} # [新增] SVG 模板
    }
    def __init__(self):
        super().__init__()
        self.icon_generator = IconGenerator()
        self.batch_items: List[str] = []
        self.presets: Dict[str, Dict] = {}
        self.current_options: Dict[str, Any] = self._get_default_options()
        self.undo_stack = QUndoStack(self)
        self.setAcceptDrops(True)
        self.thread_pool = QThreadPool.globalInstance()
        self.active_workers = [] 
        # [新增] 定义内置样本图片的路径，用于生成预设预览
        self.preview_sample_path = "preview_sample.png"

        # [核心修正] 用于存储异步加载成功的 rembg.remove 函数
        self.rembg_remove_func: Optional[callable] = None
        # [核心修正] 用于存储已加载水印图片的 Pillow Image 对象
        self.watermark_image: Optional[Image.Image] = None
        # [核心修正] 用于追踪当前加载的水印图片的文件路径
        self.watermark_image_path: str = ""
        self.icon_library_data: Dict[str, List[str]] = {}

        self.setWindowTitle("MCD图标工具 (IconForge Pro) V4.0")
        self.setGeometry(100, 100, 1300, 850)
        self.setStyleSheet(Theme.get_qss())

        self._create_toolbar()
        self._create_central_widget()
        self._create_docks()
        self._create_statusbar()
        self._connect_signals()
        
        self.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowNestedDocks)
        self.setTabPosition(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea, QTabWidget.North)
        self._load_presets()

        # [核心修正] 在UI完全加载后，启动 rembg 后台初始化
        self._initialize_rembg_async()
        self._initialize_library_async()
    
    # --- 添加一个新的方法 ---
    def _initialize_rembg_async(self):
        """启动一个后台任务来加载 rembg 库。"""
        self.statusBar().showMessage("正在初始化背景移除模块，请稍候...")
        self.remove_bg_cb.setEnabled(False)
        self.remove_bg_cb.setToolTip("正在加载 rembg 模块...")

        worker = RembgInitializer()
        worker.signals.finished.connect(self._on_rembg_initialized)
        
        # [核心修正] 将 worker 添加到 active_workers 列表以保持其存活
        self.active_workers.append(worker)
        worker.signals.finished.connect(lambda: self.active_workers.remove(worker)) # 任务完成后自动移除

        self.thread_pool.start(worker)

    # --- 添加一个新的槽函数 ---
    def _on_rembg_initialized(self, success: bool, remove_function: Optional[callable]):
        """当 rembg 初始化完成后，此槽函数被调用。"""
        global REMBG_AVAILABLE
        if success:
            REMBG_AVAILABLE = True
            self.rembg_remove_func = remove_function
            self.remove_bg_cb.setEnabled(True)
            self.remove_bg_cb.setToolTip("启用或禁用背景移除功能 (由 rembg 提供)")
            self.statusBar().showMessage("背景移除功能已准备就绪。", 5000)
        else:
            REMBG_AVAILABLE = False
            self.remove_bg_cb.setToolTip("rembg 模块加载失败，此功能不可用。")
            self.statusBar().showMessage("背景移除模块加载失败。", 5000)

    def _initialize_library_async(self):
        """
        [已修正] 启动一个后台任务来扫描本地图标库。
        现在会正确管理 worker 的生命周期，防止其被意外销毁。
        """
        self.statusBar().showMessage("正在加载图标库...")
        
        worker = LibraryScanner()
        worker.signals.finished.connect(self._on_library_loaded)
        worker.signals.progress.connect(lambda cur, tot, msg: self.statusBar().showMessage(msg))
        
        # [核心修正] 将 worker 添加到 active_workers 列表以保持其存活，
        # 并在其任务完成后（finished信号发出时）自动从列表中移除。
        self.active_workers.append(worker)
        worker.signals.finished.connect(lambda: self.active_workers.remove(worker))

        self.thread_pool.start(worker)
    def _on_library_progress(self, current, total, message):
        """更新图标库下载/解压的进度对话框。"""
        if hasattr(self, 'library_progress_dialog'):
            self.library_progress_dialog.setMaximum(total)
            self.library_progress_dialog.setValue(current)
            self.library_progress_dialog.setLabelText(message)
    def _on_library_loaded(self, library_data: dict):
        """当图标库扫描完成后，此槽函数被调用。"""
        self.icon_library_data = library_data
        if not library_data:
            self.statusBar().showMessage("图标库为空或未找到。", 5000)
            # 可以在“图标库”选项卡中显示一个“空”状态的提示
            return
        
        self.library_categories.clear()
        self.library_categories.addItems(self.icon_library_data.keys())
        # 默认选中第一个分类并加载其图标
        if self.library_categories.count() > 0:
            self.library_categories.setCurrentRow(0)
        
        self.statusBar().showMessage("图标库已加载。", 5000)

    def _on_library_category_changed(self):
        """当用户选择一个新的图标分类时，更新右侧的图标展示区。"""
        self.library_icons.clear()
        selected_item = self.library_categories.currentItem()
        if not selected_item:
            return
            
        category = selected_item.text()
        if category in self.icon_library_data:
            icon_paths = self.icon_library_data[category]
            for path in icon_paths:
                # 创建列表项，但不立即加载图标
                item = QListWidgetItem(os.path.splitext(os.path.basename(path))[0])
                item.setData(Qt.UserRole, path)
                item.setToolTip(path)
                # 先设置一个占位符或留空
                self.library_icons.addItem(item)
                # 启动后台工作器来异步加载缩略图
                worker = ThumbnailWorker(item, path, self.library_icons.iconSize())
                worker.signals.finished.connect(self._on_thumbnail_ready) # 复用已有的槽函数
                self.thread_pool.start(worker)

    def _on_library_icon_activated(self, item: QListWidgetItem):
        """当用户双击图标库中的一个图标时，将其添加到“我的文件”列表。"""
        icon_path = item.data(Qt.UserRole)
        if icon_path:
            # 1. 添加文件到处理批次
            self._add_files_to_batch([icon_path])
            
            # 2. 切换到“我的文件”选项卡
            self.source_tabs.setCurrentIndex(0) # 假设“我的文件”是第一个选项卡
            
            # 3. 在列表中找到并选中刚刚添加的项
            # (这是一个小优化，确保用户能立即看到它)
            for i in range(self.batch_list.count()):
                list_item = self.batch_list.item(i)
                if list_item.data(Qt.UserRole) == icon_path:
                    self.batch_list.setCurrentItem(list_item)
                    break
    # --- UI 创建辅助函数 ---
    def _create_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        title = QLabel("MCD图标工具   作者：跳舞的火公子")
        title.setObjectName("NavTitleLabel")
        toolbar.addWidget(title)
        
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        toolbar.addWidget(spacer)
        
        self.add_files_btn = QPushButton("添加文件")
        self.add_folder_btn = QPushButton("添加文件夹")
        self.clear_batch_btn = QPushButton("清空列表")
        for btn in [self.add_files_btn, self.add_folder_btn, self.clear_batch_btn]:
            btn.setProperty("cssClass", "toolbar")
            toolbar.addWidget(btn)
        self.addToolBar(toolbar)

    def _create_central_widget(self):
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.central_header = QLabel("未选择文件")
        self.central_header.setFixedHeight(40)
        self.central_header.setStyleSheet(f"""
            background-color: {Theme.LIGHT['bg-secondary']};
            padding-left: 15px;
            font-weight: bold;
            border-bottom: 1px solid {Theme.LIGHT['border-primary']};
        """)
        
        self.main_preview = QLabel("请从左侧列表选择一张图片")
        self.main_preview.setAlignment(Qt.AlignCenter)
        self.main_preview.setStyleSheet(f"background-color: {Theme.LIGHT['bg-tertiary']};")
        
        layout.addWidget(self.central_header)
        layout.addWidget(self.main_preview, 1)
        self.setCentralWidget(main_widget)

    def _create_docks(self):
        """
        [已重写] 创建左右两侧的可停靠面板。
        左侧源浏览器现在包含“我的文件”和“图标库”两个选项卡。
        """
        # --- 左侧：源浏览器 ---
        left_dock = QDockWidget("源浏览器", self)
        left_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        left_dock.setMinimumWidth(320) # 稍微加宽以容纳新UI
        left_dock.setTitleBarWidget(QWidget())
        left_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)

        # 创建一个包含选项卡和内容区域的容器
        left_dock_content = QWidget()
        left_layout = QVBoxLayout(left_dock_content)
        left_layout.setSpacing(0)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. [新增] 创建顶部选项卡栏
        self.source_tabs = QTabWidget()
        left_layout.addWidget(self.source_tabs)
        
        # --- 选项卡1: 我的文件 ---
        my_files_widget = QWidget()
        my_files_layout = QVBoxLayout(my_files_widget)
        my_files_layout.setContentsMargins(0,0,0,0)
        
        # 使用 QStackedWidget 来切换“空列表”和“文件列表”
        self.left_stack = QStackedWidget()
        self.empty_list_widget = EmptyListWidget()
        self.empty_list_widget.folder_icon_clicked.connect(self._add_folder_to_batch)
        self.batch_list = QListWidget()
        self.batch_list.setIconSize(QSize(48, 48))
        self.batch_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.left_stack.addWidget(self.empty_list_widget)
        self.left_stack.addWidget(self.batch_list)
        
        my_files_layout.addWidget(self.left_stack)
        self.source_tabs.addTab(my_files_widget, "我的文件")
        self.left_stack.setCurrentWidget(self.empty_list_widget)

        # --- [新增] 选项卡2: 图标库 ---
        library_widget = QWidget()
        library_layout = QHBoxLayout(library_widget)
        library_layout.setSpacing(5)
        
        # 图标库左侧：分类列表
        self.library_categories = QListWidget()
        self.library_categories.setMaximumWidth(120)
        
        # 图标库右侧：图标展示区
        self.library_icons = QListWidget()
        self.library_icons.setViewMode(QListWidget.IconMode)
        self.library_icons.setIconSize(QSize(64, 64))
        self.library_icons.setResizeMode(QListWidget.Adjust)
        self.library_icons.setSpacing(10)
        
        library_layout.addWidget(self.library_categories)
        library_layout.addWidget(self.library_icons)
        self.source_tabs.addTab(library_widget, "图标库")

        # --- 最终设置 ---
        left_dock.setWidget(left_dock_content)
        self.addDockWidget(Qt.LeftDockWidgetArea, left_dock)

        # --- 右侧：属性检查器 (保持不变) ---
        right_dock = QDockWidget("属性检查器", self)
        right_dock.setAllowedAreas(Qt.RightDockWidgetArea)
        right_dock.setMinimumWidth(380)
        right_dock.setTitleBarWidget(QWidget())
        right_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        
        self.inspector_tabs = QTabWidget()
        self._create_process_tab()
        self._create_output_tab()
        self._create_presets_tab()
        self._create_history_tab()
        
        right_dock.setWidget(self.inspector_tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, right_dock)


    def dragEnterEvent(self, event):
        """处理文件拖拽进入主窗口区域的事件。"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        处理文件在主窗口区域释放的事件。
        [已修正] 增加了对拖拽 .svg 文件的支持。
        """
        urls = event.mimeData().urls()
        files_to_add = []
        
        # [核心修正] 定义支持的文件扩展名元组
        supported_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.svg')

        for url in urls:
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    for f in os.listdir(path):
                        # 使用 .endswith(supported_extensions) 进行检查
                        if f.lower().endswith(supported_extensions):
                            files_to_add.append(os.path.join(path, f))
                # 使用 .endswith(supported_extensions) 进行检查
                elif path.lower().endswith(supported_extensions):
                    files_to_add.append(path)
        
        if files_to_add:
            self._add_files_to_batch(files_to_add)

    def _create_process_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 15, 10, 10)

        # --- 卡片1: 基础图像处理 (大部分不变) ---
        base_card = CardWidget("图像处理")
        proc_layout = QGridLayout(base_card.contentWidget())
        
        self.padding_slider, self.padding_label = self._create_slider_with_label(0, 0, 80, "%")
        self.radius_slider, self.radius_label = self._create_slider_with_label(0, 0, 100, "%")
        self.color_overlay_cb = QCheckBox("颜色叠加:")
        self.color_overlay_btn = QPushButton()
        self._update_color_btn(self.color_overlay_btn)
        self.remove_bg_cb = QCheckBox("移除背景")
        self.remove_bg_cb.setEnabled(False) # 初始禁用，等待异步加载
        self.fill_bg_cb = QCheckBox("填充背景色:")
        self.bg_color_btn = QPushButton()
        self._update_color_btn(self.bg_color_btn, "#ffffff")

        proc_layout.addWidget(QLabel("内边距:"), 0, 0); proc_layout.addWidget(self.padding_slider, 0, 1); proc_layout.addWidget(self.padding_label, 0, 2)
        proc_layout.addWidget(QLabel("圆角半径:"), 1, 0); proc_layout.addWidget(self.radius_slider, 1, 1); proc_layout.addWidget(self.radius_label, 1, 2)
        overlay_layout = QHBoxLayout(); overlay_layout.addWidget(self.color_overlay_cb); overlay_layout.addWidget(self.color_overlay_btn); overlay_layout.addStretch()
        proc_layout.addLayout(overlay_layout, 2, 0, 1, 3)
        proc_layout.addWidget(self.remove_bg_cb, 3, 0, 1, 3)
        bg_layout = QHBoxLayout(); bg_layout.addWidget(self.fill_bg_cb); bg_layout.addWidget(self.bg_color_btn); bg_layout.addStretch()
        proc_layout.addLayout(bg_layout, 4, 0, 1, 3)
        
        self.reset_options_btn = QPushButton("恢复默认")
        reset_layout = QHBoxLayout(); reset_layout.addStretch(); reset_layout.addWidget(self.reset_options_btn)
        proc_layout.addLayout(reset_layout, 5, 0, 1, 3)

        self.color_overlay_btn.setEnabled(self.color_overlay_cb.isChecked())
        self.bg_color_btn.setEnabled(self.fill_bg_cb.isChecked())

        # --- [新增] 卡片2: 高级效果 ---
        adv_card = CardWidget("高级效果")
        adv_layout = QVBoxLayout(adv_card.contentWidget())

        # 1. 图像校正组
        correction_group = QGroupBox("图像校正")
        correction_layout = QGridLayout(correction_group)
        self.brightness_slider, self.brightness_label = self._create_slider_with_label(0, -100, 100, "%")
        self.contrast_slider, self.contrast_label = self._create_slider_with_label(0, -100, 100, "%")
        self.saturation_slider, self.saturation_label = self._create_slider_with_label(0, -100, 100, "%")
        correction_layout.addWidget(QLabel("亮度:"), 0, 0); correction_layout.addWidget(self.brightness_slider, 0, 1); correction_layout.addWidget(self.brightness_label, 0, 2)
        correction_layout.addWidget(QLabel("对比度:"), 1, 0); correction_layout.addWidget(self.contrast_slider, 1, 1); correction_layout.addWidget(self.contrast_label, 1, 2)
        correction_layout.addWidget(QLabel("饱和度:"), 2, 0); correction_layout.addWidget(self.saturation_slider, 2, 1); correction_layout.addWidget(self.saturation_label, 2, 2)
        
        # 2. 阴影/描边组
        # [核心修正] 使用 self.fx_group
        self.fx_group = QGroupBox("阴影与描边")
        self.fx_group.setCheckable(True) # 总开关
        fx_layout = QVBoxLayout(self.fx_group)
        
        self.fx_mode_group = QButtonGroup(self)
        self.fx_shadow_rb = QRadioButton("阴影")
        self.fx_stroke_rb = QRadioButton("描边")
        self.fx_mode_group.addButton(self.fx_shadow_rb, 0)
        self.fx_mode_group.addButton(self.fx_stroke_rb, 1)
        self.fx_shadow_rb.setChecked(True)
        
        mode_layout = QHBoxLayout(); mode_layout.addWidget(self.fx_shadow_rb); mode_layout.addWidget(self.fx_stroke_rb); mode_layout.addStretch()
        
        self.fx_stack = QStackedWidget()
        
        # 阴影设置面板
        shadow_widget = QWidget()
        shadow_layout = QGridLayout(shadow_widget)
        self.shadow_color_btn = QPushButton(); self._update_color_btn(self.shadow_color_btn, "#000000")
        self.shadow_blur_slider, self.shadow_blur_label = self._create_slider_with_label(5, 0, 20, "px")
        self.shadow_x_slider, self.shadow_x_label = self._create_slider_with_label(5, -20, 20, "px")
        self.shadow_y_slider, self.shadow_y_label = self._create_slider_with_label(5, -20, 20, "px")
        shadow_layout.addWidget(QLabel("颜色:"), 0, 0); shadow_layout.addWidget(self.shadow_color_btn, 0, 1)
        shadow_layout.addWidget(QLabel("模糊:"), 1, 0); shadow_layout.addWidget(self.shadow_blur_slider, 1, 1); shadow_layout.addWidget(self.shadow_blur_label, 1, 2)
        shadow_layout.addWidget(QLabel("X偏移:"), 2, 0); shadow_layout.addWidget(self.shadow_x_slider, 2, 1); shadow_layout.addWidget(self.shadow_x_label, 2, 2)
        shadow_layout.addWidget(QLabel("Y偏移:"), 3, 0); shadow_layout.addWidget(self.shadow_y_slider, 3, 1); shadow_layout.addWidget(self.shadow_y_label, 3, 2)
        
        # 描边设置面板
        stroke_widget = QWidget()
        stroke_layout = QGridLayout(stroke_widget)
        self.stroke_color_btn = QPushButton(); self._update_color_btn(self.stroke_color_btn, "#FFFFFF")
        self.stroke_width_slider, self.stroke_width_label = self._create_slider_with_label(2, 1, 10, "px")
        stroke_layout.addWidget(QLabel("颜色:"), 0, 0); stroke_layout.addWidget(self.stroke_color_btn, 0, 1)
        stroke_layout.addWidget(QLabel("宽度:"), 1, 0); stroke_layout.addWidget(self.stroke_width_slider, 1, 1); stroke_layout.addWidget(self.stroke_width_label, 1, 2)
        
        self.fx_stack.addWidget(shadow_widget)
        self.fx_stack.addWidget(stroke_widget)
        
        fx_layout.addLayout(mode_layout)
        fx_layout.addWidget(self.fx_stack)
        self.fx_mode_group.buttonClicked.connect(lambda btn: self.fx_stack.setCurrentIndex(self.fx_mode_group.id(btn)))

        # 3. 水印组
        # [核心修正] 使用 self.watermark_group
        self.watermark_group = QGroupBox("水印/角标")
        self.watermark_group.setCheckable(True)
        watermark_layout = QVBoxLayout(self.watermark_group)
        
        wm_file_layout = QHBoxLayout()
        self.watermark_select_btn = QPushButton("选择图片...")
        self.watermark_path_label = QLabel("未选择文件")
        self.watermark_path_label.setStyleSheet("font-size: 8pt; color: grey;")
        wm_file_layout.addWidget(self.watermark_select_btn)
        wm_file_layout.addWidget(self.watermark_path_label, 1)
        
        wm_props_layout = QGridLayout()
        self.watermark_size_slider, self.watermark_size_label = self._create_slider_with_label(20, 5, 50, "%")
        self.watermark_opacity_slider, self.watermark_opacity_label = self._create_slider_with_label(50, 0, 100, "%")
        wm_props_layout.addWidget(QLabel("大小:"), 0, 0); wm_props_layout.addWidget(self.watermark_size_slider, 0, 1); wm_props_layout.addWidget(self.watermark_size_label, 0, 2)
        wm_props_layout.addWidget(QLabel("不透明度:"), 1, 0); wm_props_layout.addWidget(self.watermark_opacity_slider, 1, 1); wm_props_layout.addWidget(self.watermark_opacity_label, 1, 2)
        
        self.watermark_pos_group = QButtonGroup(self)
        pos_grid = QGridLayout()
        pos_names = ['top_left', 'top_center', 'top_right', 'mid_left', 'center', 'mid_right', 'bottom_left', 'bottom_center', 'bottom_right']
        for i, name in enumerate(pos_names):
            rb = QRadioButton(); rb.setFixedSize(20, 20)
            self.watermark_pos_group.addButton(rb, i)
            pos_grid.addWidget(rb, i // 3, i % 3)
        self.watermark_pos_group.button(8).setChecked(True) # Default to bottom right

        watermark_layout.addLayout(wm_file_layout)
        watermark_layout.addLayout(wm_props_layout)
        watermark_layout.addWidget(QLabel("位置:"))
        watermark_layout.addLayout(pos_grid)
        
        adv_layout.addWidget(correction_group)
        adv_layout.addWidget(self.fx_group)
        adv_layout.addWidget(self.watermark_group)
        
        # 将所有卡片添加到主布局
        layout.addWidget(base_card)
        layout.addWidget(adv_card)
        layout.addStretch()
        self.inspector_tabs.addTab(widget, "🎨 处理")
    def _create_output_tab(self):
        """
        [已重构] 创建“输出”选项卡，区分“生成当前”和“批量生成”操作。
        [新增] 增加了对SVG导出模式的UI支持（警告标签和单列布局）。
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        layout.setContentsMargins(10, 15, 10, 10)
        
        # --- 卡片1: 平台模板 ---
        template_card = CardWidget("平台模板")
        template_layout = QGridLayout(template_card.contentWidget())
        self.template_group = QButtonGroup(self)
        
        # 遍历所有模板并创建单选按钮
        for i, name in enumerate(self.PLATFORM_TEMPLATES.keys()):
            radio = QRadioButton(name)
            self.template_group.addButton(radio, i)
            # [修正] 改为单列布局，以更好地适应新添加的模板选项
            template_layout.addWidget(radio, i, 0)
        
        self.template_group.button(0).setChecked(True)

        # [新增] SVG 模式下的警告标签
        self.svg_warning_label = QLabel(
            "ℹ️ SVG导出模式下，仅“颜色叠加”生效。\n源文件也必须是SVG。"
        )
        self.svg_warning_label.setStyleSheet(
            f"color: {Theme.LIGHT['info']}; background-color: #eff6ff; "
            f"border: 1px solid #dbeafe; border-radius: 4px; padding: 8px;"
        )
        self.svg_warning_label.setWordWrap(True)
        self.svg_warning_label.hide() # 默认隐藏，由 _on_template_changed 控制显示
        
        # 将警告标签添加到模板列表的下方
        template_layout.addWidget(self.svg_warning_label, len(self.PLATFORM_TEMPLATES), 0)

        # --- 卡片2: 自定义尺寸 ---
        sizes_card = CardWidget("自定义尺寸")
        sizes_layout = QGridLayout(sizes_card.contentWidget())
        self.size_checkboxes: Dict[int, QCheckBox] = {}
        standard_sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
        for i, size in enumerate(standard_sizes):
            cb = QCheckBox(f"{size}x{size}")
            self.size_checkboxes[size] = cb
            sizes_layout.addWidget(cb, i % 5, i // 5)

        # --- 卡片3: 导出当前选中的图标 ---
        export_current_card = CardWidget("导出当前图标")
        export_current_layout = QVBoxLayout(export_current_card.contentWidget())
        self.generate_current_button = QPushButton("📄 生成当前选中图标")
        self.generate_current_button.setStyleSheet(f"background-color: {Theme.LIGHT['info']}; color: white;")
        export_current_layout.addWidget(self.generate_current_button)

        # --- 卡片4: 批量导出所有图标 ---
        export_batch_card = CardWidget("批量导出")
        export_batch_layout = QVBoxLayout(export_batch_card.contentWidget())
        
        prefix_layout = QHBoxLayout()
        self.prefix_label = QLabel("PNG文件名前缀:")
        self.prefix_edit = QLineEdit("icon")
        prefix_layout.addWidget(self.prefix_label)
        prefix_layout.addWidget(self.prefix_edit)
        export_batch_layout.addLayout(prefix_layout)

        self.generate_batch_button = QPushButton("🚀 批量生成所有图标")
        self.generate_batch_button.setObjectName("PrimaryButton")
        self.generate_batch_button.setFixedHeight(50)
        export_batch_layout.addWidget(self.generate_batch_button)

        # 将所有卡片添加到主布局中
        layout.addWidget(template_card)
        layout.addWidget(sizes_card)
        layout.addWidget(export_current_card)
        layout.addWidget(export_batch_card)
        layout.addStretch()
        
        self.inspector_tabs.addTab(widget, "📤 输出")
        
        # 初始化UI状态
        self._on_template_changed()

    def _set_svg_mode_ui(self, is_svg_mode: bool):
        """[新增] 根据是否为SVG导出模式，启用或禁用相关UI控件。"""
        # 这些控件在SVG模式下无效，应禁用
        controls_to_disable = [
            self.padding_slider, self.radius_slider, self.remove_bg_cb,
            self.fill_bg_cb, self.reset_options_btn,
            # 高级效果中的所有控件
            self.brightness_slider, self.contrast_slider, self.saturation_slider,
            self.fx_group, self.watermark_group
        ]
        
        for control in controls_to_disable:
            control.setEnabled(not is_svg_mode)
            
        # “颜色叠加”是唯一在SVG模式下仍可用的选项
        self.color_overlay_cb.setEnabled(True)
        self.color_overlay_btn.setEnabled(self.color_overlay_cb.isChecked())
        
        # 显示或隐藏警告信息
        self.svg_warning_label.setVisible(is_svg_mode)
    def _create_presets_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setSpacing(15); layout.setContentsMargins(10,15,10,10)
        card = CardWidget("预设管理"); card_layout = QVBoxLayout(card.contentWidget())
        
        self.presets_list = QListWidget()
        card_layout.addWidget(self.presets_list, 1)
        
        btn_layout = QGridLayout()
        self.preset_name_edit = QLineEdit("我的预设"); btn_layout.addWidget(self.preset_name_edit, 0, 0, 1, 2)
        self.save_preset_btn = QPushButton("保存/更新"); btn_layout.addWidget(self.save_preset_btn, 1, 0)
        self.delete_preset_btn = QPushButton("删除选中"); btn_layout.addWidget(self.delete_preset_btn, 1, 1)
        card_layout.addLayout(btn_layout)

        layout.addWidget(card); layout.addStretch()
        self.inspector_tabs.addTab(widget, "⚙️ 预设")

    def _create_history_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); layout.setContentsMargins(10,15,10,10)
        card = CardWidget("操作历史"); card_layout = QVBoxLayout(card.contentWidget())
        history_view = QUndoView(self.undo_stack)
        history_view.setEmptyLabel("尚无操作")
        card_layout.addWidget(history_view)
        layout.addWidget(card); layout.addStretch()
        self.inspector_tabs.addTab(widget, "📜 历史")

    def _create_statusbar(self): self.statusBar().showMessage("就绪。")
    
    def _connect_signals(self):
        """连接所有UI组件的信号到本类的槽函数。"""
        # --- 工具栏与源浏览器信号 ---
        self.add_files_btn.clicked.connect(lambda: self._add_files_to_batch())
        self.add_folder_btn.clicked.connect(self._add_folder_to_batch)
        self.clear_batch_btn.clicked.connect(self._clear_batch)
        self.batch_list.currentItemChanged.connect(self._on_batch_selection_changed)
        
        # --- 基础处理选项卡信号 ---
        self.padding_slider.sliderReleased.connect(lambda: self._on_property_changed('padding', self.padding_slider.value(), f"调整内边距"))
        self.radius_slider.sliderReleased.connect(lambda: self._on_property_changed('radius', self.radius_slider.value(), f"调整圆角"))
        self.color_overlay_cb.stateChanged.connect(lambda s: self._on_property_changed('color_overlay_enabled', bool(s), "切换颜色叠加"))
        self.color_overlay_btn.clicked.connect(lambda: self._select_color_for_btn(self.color_overlay_btn, 'color_overlay', "更改叠加颜色"))
        self.remove_bg_cb.stateChanged.connect(lambda s: self._on_property_changed('remove_bg', bool(s), "切换移除背景"))
        self.fill_bg_cb.stateChanged.connect(lambda s: self._on_property_changed('bg_color', self.bg_color_btn.property("color") if s else None, "切换填充背景"))
        self.bg_color_btn.clicked.connect(lambda: self._select_color_for_btn(self.bg_color_btn, 'bg_color', "更改背景色", self.fill_bg_cb))
        self.color_overlay_cb.stateChanged.connect(self.color_overlay_btn.setEnabled)
        self.fill_bg_cb.stateChanged.connect(self.bg_color_btn.setEnabled)
        self.reset_options_btn.clicked.connect(self._reset_process_options)

        # --- [新增] 高级效果信号 ---
        # 图像校正
        self.brightness_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_brightness', self.brightness_slider.value(), "调整亮度"))
        self.contrast_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_contrast', self.contrast_slider.value(), "调整对比度"))
        self.saturation_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_saturation', self.saturation_slider.value(), "调整饱和度"))
        
        # 阴影/描边
        self.fx_group.toggled.connect(lambda on: self._on_property_changed('adv_fx_enabled', on, "切换阴影/描边"))
        self.fx_mode_group.buttonClicked.connect(lambda btn: self._on_property_changed('adv_fx_mode', 'stroke' if self.fx_mode_group.id(btn) == 1 else 'shadow', "切换效果模式"))
        self.shadow_color_btn.clicked.connect(lambda: self._select_color_for_btn(self.shadow_color_btn, 'adv_shadow_color', "更改阴影颜色"))
        self.shadow_blur_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_shadow_blur', self.shadow_blur_slider.value(), "调整阴影模糊"))
        self.shadow_x_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_shadow_offset_x', self.shadow_x_slider.value(), "调整阴影X偏移"))
        self.shadow_y_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_shadow_offset_y', self.shadow_y_slider.value(), "调整阴影Y偏移"))
        self.stroke_color_btn.clicked.connect(lambda: self._select_color_for_btn(self.stroke_color_btn, 'adv_stroke_color', "更改描边颜色"))
        self.stroke_width_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_stroke_width', self.stroke_width_slider.value(), "调整描边宽度"))

        # 水印
        self.watermark_group.toggled.connect(lambda on: self._on_property_changed('adv_watermark_enabled', on, "切换水印"))
        self.watermark_select_btn.clicked.connect(self._select_watermark_image)
        self.watermark_pos_group.buttonClicked.connect(self._on_watermark_pos_changed)
        self.watermark_size_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_watermark_size', self.watermark_size_slider.value(), "调整水印大小"))
        self.watermark_opacity_slider.sliderReleased.connect(lambda: self._on_property_changed('adv_watermark_opacity', self.watermark_opacity_slider.value(), "调整水印不透明度"))

        # --- 输出选项卡信号 ---
        self.template_group.buttonClicked.connect(self._on_template_changed)
        self.generate_current_button.clicked.connect(self._start_single_generation)
        self.generate_batch_button.clicked.connect(self._start_batch_generation)
        
        # --- 预设选项卡信号 ---
        self.presets_list.itemClicked.connect(self._on_preset_selected)
        self.save_preset_btn.clicked.connect(self._save_preset)
        self.delete_preset_btn.clicked.connect(self._delete_preset)

        # --- [新增] 图标库信号 ---
        self.library_categories.currentItemChanged.connect(self._on_library_category_changed)
        self.library_icons.itemDoubleClicked.connect(self._on_library_icon_activated)
    def _on_watermark_pos_changed(self, button):
        pos_names = ['top_left', 'top_center', 'top_right', 'mid_left', 'center', 'mid_right', 'bottom_left', 'bottom_center', 'bottom_right']
        pos_id = self.watermark_pos_group.id(button)
        self._on_property_changed('adv_watermark_pos', pos_names[pos_id], "更改水印位置")
    # --- 槽函数与核心逻辑 ---
    def _on_property_changed(self, key: str, value: Any, description: str):
        if self.current_options.get(key) != value:
            command = ModifyOptionsCommand(self, key, value, description)
            self.undo_stack.push(command)

    def _update_ui_from_options(self, block_signals=True):
        opts = self.current_options
        widgets_to_block = [
            self.padding_slider, self.radius_slider, self.color_overlay_cb,
            self.remove_bg_cb, self.fill_bg_cb, self.brightness_slider,
            self.contrast_slider, self.saturation_slider, self.fx_group,
            self.fx_shadow_rb, self.fx_stroke_rb, self.shadow_blur_slider,
            self.shadow_x_slider, self.shadow_y_slider, self.stroke_width_slider,
            self.watermark_group, self.watermark_size_slider, self.watermark_opacity_slider
        ]
        # Block signals to prevent feedback loops
        if block_signals: [w.blockSignals(True) for w in widgets_to_block]
        self.watermark_pos_group.blockSignals(True)

        # 基础选项
        self.padding_slider.setValue(opts.get('padding', 0))
        self.radius_slider.setValue(opts.get('radius', 0))
        self.color_overlay_cb.setChecked(opts.get('color_overlay_enabled', False))
        self._update_color_btn(self.color_overlay_btn, opts.get('color_overlay', '#4f46e5'))
        self.remove_bg_cb.setChecked(opts.get('remove_bg', False))
        self.fill_bg_cb.setChecked(opts.get('bg_color') is not None)
        if opts.get('bg_color'): self._update_color_btn(self.bg_color_btn, opts['bg_color'])

        # 图像校正
        self.brightness_slider.setValue(opts.get('adv_brightness', 0))
        self.contrast_slider.setValue(opts.get('adv_contrast', 0))
        self.saturation_slider.setValue(opts.get('adv_saturation', 0))

        # 阴影/描边
        self.fx_group.setChecked(opts.get('adv_fx_enabled', False))
        if opts.get('adv_fx_mode') == 'stroke':
            self.fx_stroke_rb.setChecked(True)
            self.fx_stack.setCurrentIndex(1)
        else:
            self.fx_shadow_rb.setChecked(True)
            self.fx_stack.setCurrentIndex(0)
        self._update_color_btn(self.shadow_color_btn, opts.get('adv_shadow_color', '#000000'))
        self.shadow_blur_slider.setValue(opts.get('adv_shadow_blur', 5))
        self.shadow_x_slider.setValue(opts.get('adv_shadow_offset_x', 5))
        self.shadow_y_slider.setValue(opts.get('adv_shadow_offset_y', 5))
        self._update_color_btn(self.stroke_color_btn, opts.get('adv_stroke_color', '#ffffff'))
        self.stroke_width_slider.setValue(opts.get('adv_stroke_width', 2))

        # 水印
        self.watermark_group.setChecked(opts.get('adv_watermark_enabled', False))
        path = opts.get('adv_watermark_path', '')
        
        # [核心修正] 使用 self.watermark_image_path 进行可靠的比较
        if path and self.watermark_image_path != path:
            if os.path.exists(path):
                try:
                    self.watermark_image = Image.open(path).convert("RGBA")
                    self.watermark_image_path = path
                except Exception as e:
                    print(f"在UI更新期间加载水印失败: {e}")
                    self.watermark_image = None
                    self.watermark_image_path = ""
            else: # Path exists in options but not on disk
                self.watermark_image = None
                self.watermark_image_path = ""
        elif not path: # Path is empty in options
            self.watermark_image = None
            self.watermark_image_path = ""

        # 更新UI标签
        if self.watermark_image and self.watermark_image_path:
            self.watermark_path_label.setText(os.path.basename(self.watermark_image_path))
        else:
            self.watermark_path_label.setText("未选择文件")
        
        pos_names = ['top_left', 'top_center', 'top_right', 'mid_left', 'center', 'mid_right', 'bottom_left', 'bottom_center', 'bottom_right']
        try:
            pos_id = pos_names.index(opts.get('adv_watermark_pos', 'bottom_right'))
            self.watermark_pos_group.button(pos_id).setChecked(True)
        except ValueError:
            self.watermark_pos_group.button(8).setChecked(True)
        
        self.watermark_size_slider.setValue(opts.get('adv_watermark_size', 20))
        self.watermark_opacity_slider.setValue(opts.get('adv_watermark_opacity', 50))
        
        # Unblock signals
        if block_signals: [w.blockSignals(False) for w in widgets_to_block]
        self.watermark_pos_group.blockSignals(False)
    def _add_files_to_batch(self, files=None):
        """
        [已升级] 异步地将文件添加到批量列表，并切换到列表视图。
        现在支持 SVG 文件类型。
        """
        if not files:
            # [核心修正] 在文件对话框的过滤器中添加 *.svg
            files, _ = QFileDialog.getOpenFileNames(self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.svg)")
        
        if files:
            # 只要有文件添加，就切换到列表视图
            self.left_stack.setCurrentWidget(self.batch_list)
            
            added_count = 0
            for f in files:
                if f not in self.batch_items:
                    self.batch_items.append(f)
                    added_count += 1
                    item = QListWidgetItem(os.path.basename(f))
                    item.setData(Qt.UserRole, f)
                    item.setToolTip(f)
                    self.batch_list.addItem(item)
                    # ThumbnailWorker 已经被修改为可以处理 .svg 文件
                    worker = ThumbnailWorker(item, f, self.batch_list.iconSize())
                    worker.signals.finished.connect(self._on_thumbnail_ready)
                    self.thread_pool.start(worker)

            self.statusBar().showMessage(f"已添加 {added_count} 个文件。当前共 {len(self.batch_items)} 个。")
    def _on_thumbnail_ready(self, item: QListWidgetItem, icon: QIcon):
        """[槽] 当后台缩略图生成完毕后，在主线程中更新列表项的图标。"""
        item.setIcon(icon)
    def _add_folder_to_batch(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if folder: self._add_files_to_batch([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))])

    def _clear_batch(self):
        """清空列表，并切换回空状态引导页。"""
        self.batch_list.clear()
        self.batch_items.clear()
        self.main_preview.setText("请从左侧列表选择一张图片")
        self.central_header.setText("未选择文件")
        self.statusBar().showMessage("列表已清空。")
        
        # [核心修改] 切换回引导页
        self.left_stack.setCurrentWidget(self.empty_list_widget)

    def _on_batch_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        if current:
            self.central_header.setText(f"当前预览: {current.text()}")
            self._update_realtime_preview()
        else:
            self.central_header.setText("未选择文件")
            self.main_preview.clear()
            self.main_preview.setText("请从左侧列表选择一张图片")

    def _update_realtime_preview(self):
        current_item = self.batch_list.currentItem()
        if not current_item:
            return
            
        source_path = current_item.data(Qt.UserRole)
        try:
            # [核心修正] 增加对 SVG 源文件的处理
            if source_path.lower().endswith('.svg'):
                renderer = QSvgRenderer(source_path)
                # 渲染到一个足够大的 QPixmap (例如 1024x1024) 以保留矢量细节
                pixmap = QPixmap(1024, 1024)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                
                # 将 QPixmap 转换为 Pillow Image 以便后续处理
                # 注意: 需要 from PyQt5.QtCore import QBuffer
                buffer = QBuffer()
                buffer.open(QBuffer.ReadWrite)
                pixmap.save(buffer, "PNG")
                source_img = Image.open(BytesIO(buffer.data()))
            else:
                # 原有的位图文件处理逻辑
                source_img = Image.open(source_path)
            
            # [核心修正] 将 remove_func 传入
            processed_img = self.icon_generator.process_image(source_img, self.current_options, self.rembg_remove_func)
            
            # 将最终处理好的 Pillow Image 转换为 QPixmap 以在 UI 中显示
            final_pixmap = self._pil_to_pixmap(processed_img)
            
            # 缩放以适应预览窗口大小并显示
            self.main_preview.setPixmap(final_pixmap.scaled(self.main_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.main_preview.setToolTip("") 
            
        except Exception as e:
            # [UX改进] 预览失败时提供更详细的用户反馈
            error_msg = f"预览更新失败: {e}"
            print(error_msg)
            self.main_preview.setText("预览失败")
            self.main_preview.setToolTip(error_msg)
            self.statusBar().showMessage(error_msg, 5000)

    def _on_template_changed(self):
        """[已重写] 当模板改变时，更新尺寸复选框并调整UI以适应SVG模式。"""
        btn = self.template_group.checkedButton()
        if not btn: return
        
        template_data = self.PLATFORM_TEMPLATES.get(btn.text())
        if not template_data: return

        sizes_to_check = template_data['sizes']
        is_icns_or_svg = template_data['format'] in ['icns', 'svg']

        for size, cb in self.size_checkboxes.items():
            cb.setChecked(size in sizes_to_check)
            cb.setEnabled(not is_icns_or_svg)
            
        # 调用新的辅助函数来处理UI状态
        self._set_svg_mode_ui(template_data['format'] == 'svg')

    # [UX改进] 1.3: 新增方法，用于重置处理选项
    def _reset_process_options(self):
        """将所有处理选项恢复为默认值，并将整个操作记录到撤销堆栈中。"""
        self.undo_stack.beginMacro("恢复默认处理选项")
        
        defaults = self._get_default_options()
        for key, default_value in defaults.items():
            if self.current_options.get(key) != default_value:
                # 复用现有的 Command 逻辑，为每个变化的属性创建一个命令
                command = ModifyOptionsCommand(self, key, default_value, f"重置 {key}")
                self.undo_stack.push(command)
        
        self.undo_stack.endMacro()
        self.statusBar().showMessage("处理选项已恢复默认。", 3000)

    def _load_presets(self):
        try:
            if os.path.exists("iconforge_presets.json"):
                with open("iconforge_presets.json", "r") as f:
                    self.presets.update(json.load(f))
        except Exception as e:
            print(f"加载预设失败: {e}")
        self._update_presets_list()

    def _save_presets(self):
        try:
            with open("iconforge_presets.json", "w") as f:
                json.dump(self.presets, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存预设失败: {e}")

    def _update_presets_list(self):
        self.presets_list.clear()
        preview_dir = "presets_previews"
        
        for name in sorted(self.presets.keys()):
            item = QListWidgetItem(name)
            
            # [新增] 尝试加载并设置预览图标
            safe_filename = "".join(c for c in name if c.isalnum() or c in " _-").rstrip()
            preview_path = os.path.join(preview_dir, f"{safe_filename}.png")
            
            if os.path.exists(preview_path):
                icon = QIcon(preview_path)
                item.setIcon(icon)
            
            self.presets_list.addItem(item)

    def _on_preset_selected(self, item: QListWidgetItem):
        name = item.text()
        self.preset_name_edit.setText(name)
        if name in self.presets:
            new_options = self.presets[name]
            # Use QUndoCommand for each property change to build a macro command
            self.undo_stack.beginMacro(f"加载预设 '{name}'")
            for key, value in new_options.items():
                if self.current_options.get(key) != value:
                    command = ModifyOptionsCommand(self, key, value, f"设置 {key}")
                    self.undo_stack.push(command)
            self.undo_stack.endMacro()
    
    def _save_preset(self):
        name = self.preset_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "无效名称", "预设名称不能为空。")
            return
        
        # 1. 保存配置数据
        self.presets[name] = self.current_options.copy()
        self._save_presets()

        # 2. [新增] 生成并保存预览图
        self._generate_and_save_preset_preview(name)

        # 3. 更新UI
        self._update_presets_list()
        self.statusBar().showMessage(f"已保存预设 '{name}'", 3000)
    def _generate_and_save_preset_preview(self, preset_name: str):
        """为指定的预设生成并保存一张预览缩略图。"""
        try:
            # 确定使用哪张图片作为样本
            source_path = ""
            current_item = self.batch_list.currentItem()
            if current_item:
                source_path = current_item.data(Qt.UserRole)
            elif os.path.exists(self.preview_sample_path):
                source_path = self.preview_sample_path
            else:
                print("警告: 找不到样本图片，无法生成预设预览。")
                return

            source_img = Image.open(source_path)
            
            # 应用当前设置生成效果图
            options = self.presets[preset_name]
            processed_img = self.icon_generator.process_image(source_img, options, self.rembg_remove_func)
            
            # 缩放到合适的尺寸
            processed_img.thumbnail((96, 96), Image.LANCZOS)
            
            # 创建一个正方形的背景以保证尺寸统一
            preview_canvas = Image.new("RGBA", (96, 96), (0,0,0,0))
            paste_pos = ((96 - processed_img.width) // 2, (96 - processed_img.height) // 2)
            preview_canvas.paste(processed_img, paste_pos, processed_img)
            
            # 保存到预览文件夹
            preview_dir = "presets_previews"
            if not os.path.exists(preview_dir):
                os.makedirs(preview_dir)
            
            # 文件名不允许包含非法字符，这里做一个简单的替换
            safe_filename = "".join(c for c in preset_name if c.isalnum() or c in " _-").rstrip()
            preview_path = os.path.join(preview_dir, f"{safe_filename}.png")
            preview_canvas.save(preview_path, "PNG")

        except Exception as e:
            print(f"为预设 '{preset_name}' 生成预览图失败: {e}")

    def _delete_preset(self):
        item = self.presets_list.currentItem()
        if not item:
            QMessageBox.warning(self, "未选择", "请先在列表中选择一个要删除的预设。")
            return
        
        name = item.text()
        if name == "默认" and name in self.presets and self.presets[name].get('is_default'): # 更严谨的判断
            QMessageBox.warning(self, "无法删除", "不能删除内置的默认预设。")
            return
            
        reply = QMessageBox.question(self, "确认", f"确定要删除预设 '{name}' 吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes and name in self.presets:
            # 1. 删除配置
            del self.presets[name]
            self._save_presets()
            
            # 2. [新增] 删除对应的预览图
            try:
                preview_dir = "presets_previews"
                safe_filename = "".join(c for c in name if c.isalnum() or c in " _-").rstrip()
                preview_path = os.path.join(preview_dir, f"{safe_filename}.png")
                if os.path.exists(preview_path):
                    os.remove(preview_path)
            except Exception as e:
                print(f"删除预设预览图失败: {e}")
                
            # 3. 更新UI
            self._update_presets_list()
    def _select_watermark_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择水印图片", "", "图片文件 (*.png)")
        if path:
            try:
                # 尝试加载图片以确保它是有效的
                self.watermark_image = Image.open(path).convert("RGBA")
                self.watermark_image_path = path # [核心修正] 更新路径追踪器
                # 使用命令系统来记录路径的更改
                self._on_property_changed('adv_watermark_path', path, "选择水印图片")
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法加载水印图片: {e}")
                self.watermark_image = None
                self.watermark_image_path = "" # [核心修正] 清空路径追踪器
                self._on_property_changed('adv_watermark_path', '', "清除水印图片")
    def _start_single_generation(self):
        """
        [新增] 启动对当前选中的单个图标的生成过程。
        """
        current_item = self.batch_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "操作无效", "请先在左侧列表中选择一个要生成的图片。")
            return
        
        source_path = current_item.data(Qt.UserRole)
        self._start_generation_process([source_path]) # 调用通用的处理函数，但只传入一个文件

    def _start_batch_generation(self):
        """
        [重命名] 启动对列表中所有图标的批量生成过程。
        """
        if not self.batch_items:
            QMessageBox.warning(self, "操作无效", "请先添加至少一张图片到处理列表。")
            return
        
        self._start_generation_process(self.batch_items) # 调用通用的处理函数，传入所有文件

    def _start_generation_process(self, items_to_process: List[str]):
        """
        [已修正] [通用处理函数] 处理指定文件列表的生成逻辑。
        - 现在会根据是单文件还是批量操作，弹出正确的文件/文件夹选择对话框。
        - 会将异步加载的 rembg 函数传递给后台工作器。
        """
        is_batch = len(items_to_process) > 1
        opts = self._get_current_options_for_generation()
        fmt = opts['format']
        
        output_path = ""
        # 仅在单文件模式下，建议的文件名才有意义
        suggested_name = os.path.splitext(os.path.basename(items_to_process[0]))[0] if not is_batch else "icon"

        # [核心修正] 根据操作类型选择正确的对话框
        if is_batch or fmt == 'png_suite':
            # 以下情况应选择目录：
            # 1. 任何批量操作 (is_batch == True)
            # 2. 单文件操作，但输出为PNG套件 (需要一个目录来存放多个PNG)
            dialog_title = "选择批量导出的目标文件夹" if is_batch else "选择保存PNG套件的文件夹"
            output_path = QFileDialog.getExistingDirectory(self, dialog_title)
        else:
            # 唯一剩下的情况：单文件输入 -> 单文件输出 (.ico 或 .icns)
            # 这种情况下才需要用户指定确切的文件名
            output_path, _ = QFileDialog.getSaveFileName(
                self, "保存图标", f"{suggested_name}.{fmt}", f"图标文件 (*.{fmt})"
            )
        
        if not output_path:
            return # 用户取消了选择

        self.progress_dialog = QProgressDialog("生成中...", "取消", 0, len(items_to_process), self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        
        # [核心修正] 创建 GenerateWorker 时传入 self.rembg_remove_func
        self.worker = GenerateWorker(self.icon_generator, items_to_process, output_path, opts, self.rembg_remove_func)
        
        self.worker.signals.progress.connect(lambda i, t, n: self.progress_dialog.setLabelText(f"{n} ({i+1}/{t})") or self.progress_dialog.setValue(i))
        self.worker.signals.finished.connect(lambda msg: (self.progress_dialog.close(), QMessageBox.information(self, "完成", msg)))
        self.worker.signals.error.connect(lambda err: (self.progress_dialog.close(), QMessageBox.critical(self, "错误", err)))
        self.progress_dialog.canceled.connect(self.worker.cancel)
        
        self.thread_pool.start(self.worker)
        self.progress_dialog.show()

    def _get_current_options_for_generation(self) -> Dict[str, Any]:
        """
        [已修正] 从UI收集最终用于生成的选项。
        此版本确保总是使用当前勾选框的状态，而不是模板的默认状态。
        """
        opts = self.current_options.copy()
        
        # 1. 确定输出格式
        template_name = self.template_group.checkedButton().text()
        fmt = self.PLATFORM_TEMPLATES[template_name]['format']
        opts['format'] = fmt

        # 2. [关键修正] 无论模板如何，都从UI重新收集当前所有被勾选的尺寸
        selected_sizes = [(s, s) for s, cb in self.size_checkboxes.items() if cb.isChecked()]
        
        # 3. 为需要尺寸的格式赋值
        if fmt == 'ico' or fmt == 'png_suite':
            opts['sizes'] = selected_sizes
        else: # for 'icns'
            opts['sizes'] = []
            
        return opts

    def _get_default_options(self) -> Dict[str, Any]:
        return {
            # --- 基础选项 ---
            'padding': 0,
            'radius': 0,
            'color_overlay_enabled': False,
            'color_overlay': '#4f46e5',
            'remove_bg': False,
            'bg_color': None,
            
            # --- [新增] 图像校正选项 ---
            'adv_brightness': 0,    # -100 to 100
            'adv_contrast': 0,      # -100 to 100
            'adv_saturation': 0,    # -100 to 100
            
            # --- [新增] 阴影与描边选项 ---
            'adv_fx_enabled': False,
            'adv_fx_mode': 'shadow', # 'shadow' or 'stroke'
            
            'adv_shadow_color': '#000000',
            'adv_shadow_blur': 5,     # 0 to 20
            'adv_shadow_offset_x': 5, # -20 to 20
            'adv_shadow_offset_y': 5, # -20 to 20
            
            'adv_stroke_color': '#ffffff',
            'adv_stroke_width': 2,    # 1 to 10
            
            # --- [新增] 水印选项 ---
            'adv_watermark_enabled': False,
            'adv_watermark_path': '',
            'adv_watermark_pos': 'bottom_right', # 9-grid position
            'adv_watermark_size': 20, # 5 to 50 percent
            'adv_watermark_opacity': 50 # 0 to 100 percent
        }

    def _create_slider_with_label(self, value, min_val, max_val, suffix):
        slider = QSlider(Qt.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(value)
        label = QLabel(f"{value}{suffix}")
        label.setMinimumWidth(40)
        slider.valueChanged.connect(lambda val, l=label: l.setText(f"{val}{suffix}"))
        return slider, label

    def _update_color_btn(self, btn: QPushButton, color_hex: str = "#4f46e5"):
        btn.setFixedSize(24, 24)
        btn.setProperty("color", color_hex)
        btn.setStyleSheet(f"background-color: {color_hex}; border: 1px solid #ccc; border-radius: 4px;")

    def _select_color_for_btn(self, btn: QPushButton, key: str, desc: str, cb_enabler: Optional[QCheckBox] = None):
        if cb_enabler and not cb_enabler.isChecked():
            cb_enabler.setChecked(True) # Automatically enable the feature
        
        current_color = QColor(btn.property("color"))
        new_color = QColorDialog.getColor(current_color, self, "选择颜色")
        if new_color.isValid():
            self._on_property_changed(key, new_color.name(), desc)

    def _pil_to_pixmap(self, img: Image.Image) -> QPixmap:
        buffer = BytesIO()
        img.save(buffer, "PNG")
        qimage = QImage.fromData(buffer.getvalue())
        return QPixmap.fromImage(qimage)

# ==============================================================================
# SECTION 4: 应用程序入口点 (APPLICATION ENTRY POINT)
# ==============================================================================
if __name__ == '__main__':
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    main_window = IconForgeWindow()
    main_window.show()
    
    sys.exit(app.exec_())