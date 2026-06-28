"""STA GUI Viewer — Qt-based DEF layout + timing path visualizer.

Usage:
    python gui_viewer.py                              # open file dialogs
    python gui_viewer.py netlist.json TOP sdc def    # pre-load from CLI
"""
import sys
import os
import math

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsItem,
    QDockWidget, QWidget, QVBoxLayout, QLabel,
    QListWidget, QToolBar, QAction, QFileDialog,
    QTreeWidget, QTreeWidgetItem, QInputDialog,
    QMessageBox, QFrame,
)
from PyQt5.QtCore import Qt, QRectF, QPointF, QThread, pyqtSignal
from PyQt5.QtGui import (
    QPen, QBrush, QColor, QPainterPath, QPainterPathStroker,
    QPainter,
)

# ── STA engine imports ────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from read_def_extended import read_def_full
from parse_cell_db import load_cell_db
from parse_sdc import load_sdc
from parse_lib import load_libs
from build_graph import build_timing_graph
from propagation import calculate_delay
from parse_cell_rank import load_gate_rank

LIB_CACHE = os.path.join(_HERE, "raw_libs.pkl")
CSV_FILE  = os.path.join(_HERE, "gate_ranking_all_cells_analysis.csv")

# ── LEF cell-size parser ──────────────────────────────────────────────────────

_LEF_CACHE_FILE = os.path.join(_HERE, "lef_sizes_cache.pkl")


def parse_lef_sizes(lef_paths, def_units=1000):
    """Return dict: cell_type -> (width_def, height_def).

    Results are cached in lef_sizes_cache.pkl keyed by (path, mtime).
    Subsequent calls with the same LEF files return instantly.
    """
    import pickle, re

    # Build cache key: sorted list of (path, mtime) for existing files
    valid = [(p, os.path.getmtime(p)) for p in lef_paths if os.path.isfile(p)]
    cache_key = tuple(sorted(valid))

    # Load cache if it matches
    if os.path.isfile(_LEF_CACHE_FILE):
        try:
            with open(_LEF_CACHE_FILE, "rb") as f:
                stored_key, sizes = pickle.load(f)
            if stored_key == cache_key:
                return sizes
        except Exception:
            pass

    # Parse: read each file at once and use findall (faster than line-by-line)
    _pair_re = re.compile(
        r'^MACRO\s+(\S+).*?^\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)',
        re.MULTILINE | re.DOTALL,
    )
    sizes = {}
    for path, _ in valid:
        text = open(path).read()
        for m in _pair_re.finditer(text):
            name = m.group(1)
            if name not in sizes:   # first match wins
                sizes[name] = (
                    round(float(m.group(2)) * def_units),
                    round(float(m.group(3)) * def_units),
                )

    # Save cache
    try:
        with open(_LEF_CACHE_FILE, "wb") as f:
            pickle.dump((cache_key, sizes), f)
    except Exception:
        pass

    return sizes


# ── Layout constants (DEF units) ──────────────────────────────────────────────
# Fallback used when a cell type is not found in LEF.
CELL_H_DEFAULT = 270   # ASAP7 row height (270 nm = 270 DEF units)
CELL_W_DEFAULT = 216   # 4 sites × 54 nm

# ── Colors ────────────────────────────────────────────────────────────────────
_C_BG        = QColor(20,  20,  35)
_C_DIE_FILL  = QColor(30,  30,  55)
_C_DIE_EDGE  = QColor(140, 160, 200)
_C_CELL_DEF  = QColor(70,  110, 180, 200)
_C_CELL_SEL  = QColor(255, 215, 50,  230)
_C_PORT      = QColor(200, 200, 80,  200)
_C_NET_LINES = QColor(80,  80,  120, 60)


def _slack_color(slack: float, wns: float) -> QColor:
    """Red (WNS) → yellow (0) → green (positive)."""
    if slack >= 0:
        t = min(slack / max(abs(wns), 1.0), 1.0)
        return QColor(50 + int(t * 30), 180 + int(t * 20), 70 + int(t * 30))
    else:
        if wns >= 0:
            return QColor(220, 50, 50)
        t = slack / wns  # 1.0 at wns, 0.0 at 0
        return QColor(220, int(200 * (1.0 - t)), 50)


# ── Timing path graphic item ──────────────────────────────────────────────────

class TimingPathItem(QGraphicsItem):
    """Draws a directed polyline with arrowheads, representing one timing path."""

    ARROW = 12   # arrowhead size in DEF units * scale

    def __init__(self, points, slack, wns, path_nodes, scene_ref):
        super().__init__()
        self._points   = points      # [QPointF, ...]
        self.slack     = slack
        self.path_nodes = path_nodes  # [inst_name, ...]
        self._scene_ref = scene_ref
        self._selected  = False

        self._color = _slack_color(slack, wns)
        self._color_dim = QColor(self._color)
        self._color_dim.setAlpha(80)

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(3)

        if points:
            xs = [p.x() for p in points]
            ys = [p.y() for p in points]
            m = 200
            self._brect = QRectF(min(xs) - m, min(ys) - m,
                                 max(xs) - min(xs) + 2*m,
                                 max(ys) - min(ys) + 2*m)
        else:
            self._brect = QRectF()

        txt = f"Slack: {slack:.3f} ps  Hops: {len(path_nodes)}"
        self.setToolTip(txt)

    def boundingRect(self):
        return self._brect

    def shape(self):
        if len(self._points) < 2:
            return QPainterPath()
        lp = QPainterPath()
        lp.moveTo(self._points[0])
        for p in self._points[1:]:
            lp.lineTo(p)
        stroker = QPainterPathStroker()
        stroker.setWidth(400)  # wide hit area
        return stroker.createStroke(lp)

    def paint(self, painter, option, widget=None):
        if len(self._points) < 2:
            return
        color = QColor(self._color if self._selected else self._color_dim)
        w = 120 if self._selected else 60
        pen = QPen(color, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        for i in range(len(self._points) - 1):
            p1, p2 = self._points[i], self._points[i + 1]
            painter.drawLine(p1, p2)
            self._draw_arrow(painter, p1, p2, color, w)

    def _draw_arrow(self, painter, p1, p2, color, line_w):
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        size = max(line_w * 3, 300)
        perp = size * 0.4
        ax1 = QPointF(p2.x() - ux*size + (-uy)*perp, p2.y() - uy*size + ux*perp)
        ax2 = QPointF(p2.x() - ux*size - (-uy)*perp, p2.y() - uy*size - ux*perp)
        painter.drawLine(p2, ax1)
        painter.drawLine(p2, ax2)

    def hoverEnterEvent(self, event):
        self._selected = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self._selected = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self._scene_ref:
            self._scene_ref.on_path_clicked(self)

    def set_highlight(self, on: bool):
        self._selected = on
        self.update()


# ── Cell graphic item ─────────────────────────────────────────────────────────

class CellItem(QGraphicsRectItem):
    """A clickable cell rectangle in DEF coordinates (Y already flipped)."""

    def __init__(self, inst_name, cell_type, x, y, w, h, scene_ref):
        super().__init__(x, y, w, h)
        self.inst_name = inst_name
        self.cell_type = cell_type
        self._scene_ref = scene_ref
        self._base_brush = QBrush(_C_CELL_DEF)
        self._selected = False

        self.setBrush(self._base_brush)
        self.setPen(QPen(QColor(100, 140, 220), 20))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(2)
        self.setToolTip(f"{inst_name}  [{cell_type}]")

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor(255, 255, 100), 40))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        w = 40 if self._selected else 20
        c = QColor(255, 200, 50) if self._selected else QColor(100, 140, 220)
        self.setPen(QPen(c, w))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self._scene_ref:
            self._scene_ref.on_cell_clicked(self)

    def set_slack_color(self, slack: float, wns: float):
        col = _slack_color(slack, wns)
        col.setAlpha(200)
        self._base_brush = QBrush(col)
        self.setBrush(self._base_brush)

    def set_highlight(self, on: bool):
        self._selected = on
        if on:
            self.setBrush(QBrush(_C_CELL_SEL))
            self.setPen(QPen(QColor(255, 200, 50), 60))
        else:
            self.setBrush(self._base_brush)
            self.setPen(QPen(QColor(100, 140, 220), 20))


# ── Scene ─────────────────────────────────────────────────────────────────────

class DEFScene(QGraphicsScene):
    sig_cell_clicked = pyqtSignal(object)
    sig_path_clicked = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.cell_items  = {}   # inst_name -> CellItem
        self.path_items  = []   # [TimingPathItem]
        self._sel_cell   = None
        self._sel_path   = None

    def on_cell_clicked(self, item: CellItem):
        if self._sel_cell and self._sel_cell is not item:
            self._sel_cell.set_highlight(False)
        self._sel_cell = item
        item.set_highlight(True)
        self.sig_cell_clicked.emit(item)

    def on_path_clicked(self, item: TimingPathItem):
        if self._sel_path and self._sel_path is not item:
            self._sel_path.set_highlight(False)
        self._sel_path = item
        item.set_highlight(True)
        self.sig_path_clicked.emit(item)

    def clear_selection(self):
        if self._sel_cell:
            self._sel_cell.set_highlight(False)
            self._sel_cell = None
        if self._sel_path:
            self._sel_path.set_highlight(False)
            self._sel_path = None

    def set_paths_visible(self, visible: bool):
        for p in self.path_items:
            p.setVisible(visible)

    def set_nets_visible(self, visible: bool):
        for item in self._net_items:
            item.setVisible(visible)

    def store_net_items(self, items):
        self._net_items = items


# ── View ──────────────────────────────────────────────────────────────────────

class DEFView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)   # left click = selection only
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(_C_BG))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._pan_last = None  # last mouse pos while right-dragging

    def wheelEvent(self, event):
        f = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(f, f)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._pan_last = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton:
            self._pan_last = None
            self.setCursor(Qt.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            self.fitInView(self.scene().itemsBoundingRect(), Qt.KeepAspectRatio)
        super().keyPressEvent(event)


# ── STA worker thread ─────────────────────────────────────────────────────────

class STAWorker(QThread):
    sig_progress = pyqtSignal(str)
    sig_finished = pyqtSignal(object, object, object, object, object, object, object)
    sig_error    = pyqtSignal(str)

    def __init__(self, json_f, top, sdc_f, def_f, use_net_delay, lef_paths=None):
        super().__init__()
        self.json_f    = json_f
        self.top       = top
        self.sdc_f     = sdc_f
        self.def_f     = def_f
        self.use_net_delay = use_net_delay
        self.lef_paths = lef_paths or []

    def run(self):
        try:
            self.sig_progress.emit("Loading SDC…")
            sdc_info = load_sdc(self.sdc_f)

            self.sig_progress.emit("Loading libraries…")
            raw_libs = load_libs(LIB_CACHE)
            if not raw_libs:
                self.sig_error.emit("No libraries loaded (raw_libs.pkl missing?).")
                return

            self.sig_progress.emit("Building cell DB…")
            cell_db = load_cell_db(raw_libs)

            self.sig_progress.emit("Building timing graph…")
            tg = build_timing_graph(self.json_f, self.top, cell_db, sdc_info)
            order = tg.topo_sort()

            self.sig_progress.emit("Loading gate rank…")
            _, _, type_to_cells = load_gate_rank(CSV_FILE)

            self.sig_progress.emit("Parsing DEF…")
            die, comps, nets, port_pos, comp_pos, pin_wl = read_def_full(self.def_f)

            self.sig_progress.emit("Running STA propagation…")
            net_wl_arg = pin_wl if self.use_net_delay else None
            calculate_delay(
                topo_order=order,
                cell_db=cell_db,
                sdc_data=sdc_info,
                inst_to_clocks=tg.instance_to_clocks,
                p2p_delay=None,
                type_to_cells=type_to_cells,
                net_wl=net_wl_arg,
            )

            self.sig_progress.emit("Parsing LEF sizes…")
            lef_sizes = parse_lef_sizes(self.lef_paths)

            self.sig_progress.emit("Done!")
            self.sig_finished.emit(tg, die, comps, nets, port_pos, pin_wl, lef_sizes)

        except SystemExit as e:
            self.sig_error.emit(f"Fatal error in STA engine (sys.exit called): code {e.code}\n"
                                f"Check module name and input files.")
        except Exception:
            import traceback
            self.sig_error.emit(traceback.format_exc())


# ── Detail panel ──────────────────────────────────────────────────────────────

class DetailPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self._title = QLabel("Select a cell or timing path")
        self._title.setStyleSheet(
            "font-weight:bold; font-size:13px; color:#89dceb; padding:4px;"
        )
        layout.addWidget(self._title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#45475a;")
        layout.addWidget(sep)

        self._props = QTreeWidget()
        self._props.setHeaderLabels(["Property", "Value"])
        self._props.setColumnWidth(0, 130)
        self._props.setMaximumHeight(200)
        layout.addWidget(self._props)

        layout.addWidget(QLabel("Path hops (start → end):"))
        self._hops = QListWidget()
        layout.addWidget(self._hops)
        layout.addStretch()

    def _add(self, key, value):
        QTreeWidgetItem(self._props, [key, str(value)])

    def show_cell(self, item: CellItem, tg_nodes):
        self._title.setText(f"Cell  ·  {item.inst_name}")
        self._props.clear()
        self._hops.clear()
        self._add("Instance", item.inst_name)
        self._add("Type", item.cell_type)

        # Find worst-slack node for this instance
        worst = None
        for nd in tg_nodes.values():
            if nd.inst == item.inst_name:
                if worst is None or nd.end_point_slack < worst.end_point_slack:
                    worst = nd
                # Show AT/slew from any output pin
                self._add(f"Rise AT [{nd.pin}]", f"{nd.rise_at:.3f} ps")
                self._add(f"Fall AT [{nd.pin}]", f"{nd.fall_at:.3f} ps")
                self._add(f"Rise Slew [{nd.pin}]", f"{nd.rise_slew:.3f} ps")
                self._add(f"Load [{nd.pin}]", f"{nd.load:.4f} fF")

        if worst and worst.end_point_slack < 1e17:
            self._add("Endpoint Slack", f"{worst.end_point_slack:.3f} ps")

    def show_path(self, item: TimingPathItem, tg_nodes):
        self._title.setText(f"Timing Path  ·  slack = {item.slack:.3f} ps")
        self._props.clear()
        self._hops.clear()
        self._add("Slack", f"{item.slack:.3f} ps")
        self._add("Hops", str(len(item.path_nodes)))
        self._add("Type", "Violation (neg slack)" if item.slack < 0 else "Non-critical")
        for i, inst in enumerate(item.path_nodes):
            nd_info = ""
            for nd in tg_nodes.values():
                if nd.inst == inst:
                    nd_info = f"  AT={nd.at():.1f}"
                    break
            self._hops.addItem(f"{i:3d}.  {inst}{nd_info}")


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Easy_STA — Layout Viewer")
        self.resize(1440, 900)

        self._tg         = None
        self._components = {}
        self._lef_sizes  = {}
        self._wns        = 0.0
        self._use_net_delay = True

        # CLI-preloaded paths
        self._json_f    = ""
        self._top       = ""
        self._sdc_f     = ""
        self._def_f     = ""
        self._lef_paths = []   # optional; auto-detected from contest dir if empty

        self._build_ui()
        self._apply_theme()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._scene = DEFScene()
        self._scene.sig_cell_clicked.connect(self._on_cell_clicked)
        self._scene.sig_path_clicked.connect(self._on_path_clicked)
        self._scene.store_net_items([])

        self._view = DEFView(self._scene)
        self.setCentralWidget(self._view)

        # Right dock — details
        self._detail = DetailPanel()
        dock = QDockWidget("Details", self)
        dock.setWidget(self._detail)
        dock.setMinimumWidth(270)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # Toolbar
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self._act_load = QAction("📂 Load Files", self)
        self._act_load.triggered.connect(self._load_files)
        tb.addAction(self._act_load)

        self._act_run = QAction("▶ Run STA", self)
        self._act_run.setEnabled(False)
        self._act_run.triggered.connect(self._run_sta)
        tb.addAction(self._act_run)

        tb.addSeparator()

        self._act_net_delay = QAction("Net Delay: ON", self)
        self._act_net_delay.setCheckable(True)
        self._act_net_delay.setChecked(True)
        self._act_net_delay.setToolTip(
            "Toggle wire RC delay.\n"
            "OFF → net delays are zero (ideal wires)."
        )
        self._act_net_delay.triggered.connect(self._toggle_net_delay)
        tb.addAction(self._act_net_delay)

        tb.addSeparator()

        self._act_show_paths = QAction("Paths: ON", self)
        self._act_show_paths.setCheckable(True)
        self._act_show_paths.setChecked(True)
        self._act_show_paths.triggered.connect(self._toggle_paths)
        tb.addAction(self._act_show_paths)

        self._act_show_nets = QAction("All Nets: OFF", self)
        self._act_show_nets.setCheckable(True)
        self._act_show_nets.setChecked(False)
        self._act_show_nets.triggered.connect(self._toggle_nets)
        tb.addAction(self._act_show_nets)

        tb.addSeparator()

        act_fit = QAction("⊞ Fit (F)", self)
        act_fit.triggered.connect(self._fit_view)
        tb.addAction(act_fit)

        act_clear = QAction("✕ Clear Sel", self)
        act_clear.triggered.connect(self._scene.clear_selection)
        tb.addAction(act_clear)

        # Status bar
        self._sb_label = QLabel("Ready — load files to begin.")
        self.statusBar().addWidget(self._sb_label)

    def _apply_theme(self):
        self.setStyleSheet("""
        QMainWindow,QWidget{background:#1e1e2e;color:#cdd6f4;}
        QToolBar{background:#181825;border-bottom:1px solid #45475a;padding:2px;}
        QToolBar QToolButton{background:#313244;color:#cdd6f4;border-radius:4px;
            padding:4px 10px;margin:2px;}
        QToolBar QToolButton:hover{background:#45475a;}
        QToolBar QToolButton:checked{background:#cba6f7;color:#1e1e2e;}
        QDockWidget{background:#181825;color:#cdd6f4;}
        QDockWidget::title{background:#313244;padding:4px;}
        QTreeWidget,QListWidget{background:#181825;color:#cdd6f4;
            border:1px solid #45475a;font-family:monospace;}
        QTreeWidget::item:selected,QListWidget::item:selected{background:#45475a;}
        QHeaderView::section{background:#313244;color:#cdd6f4;border:none;padding:3px;}
        QStatusBar{background:#181825;color:#a6e3a1;}
        QLabel{color:#cdd6f4;}
        """)

    # ── File loading ──────────────────────────────────────────────────────────

    @staticmethod
    def _find_lefs_near(def_f):
        """Walk upward from DEF directory looking for a lef/ folder."""
        import glob
        d = os.path.dirname(os.path.abspath(def_f))
        for _ in range(5):
            lef_dir = os.path.join(d, "lef")
            hits = glob.glob(os.path.join(lef_dir, "*.lef"))
            if hits:
                return hits
            # also check Platform/ASAP7/lef relative to repo root
            for extra in ["Platform/ASAP7/lef", "../Platform/ASAP7/lef",
                          "../../Platform/ASAP7/lef", "../../../Platform/ASAP7/lef"]:
                hits = glob.glob(os.path.join(d, extra, "*.lef"))
                if hits:
                    return hits
            d = os.path.dirname(d)
        return []

    def _load_files(self):
        json_f, _ = QFileDialog.getOpenFileName(
            self, "Open JSON Netlist", _HERE, "JSON (*.json)")
        if not json_f:
            return
        sdc_f, _ = QFileDialog.getOpenFileName(
            self, "Open SDC File", _HERE, "SDC (*.sdc)")
        if not sdc_f:
            return
        def_f, _ = QFileDialog.getOpenFileName(
            self, "Open DEF File", _HERE, "DEF (*.def)")
        if not def_f:
            return

        # Auto-detect module name from JSON
        default_top = ""
        try:
            import json as _json
            mods = list(_json.load(open(json_f)).get("modules", {}).keys())
            if mods:
                default_top = mods[0]
        except Exception:
            pass

        top, ok = QInputDialog.getText(
            self, "Top Module", "Enter top module name:", text=default_top)
        if not ok or not top.strip():
            return

        self._json_f    = json_f
        self._sdc_f     = sdc_f
        self._def_f     = def_f
        self._top       = top.strip()
        self._lef_paths = self._find_lefs_near(def_f)
        self._act_run.setEnabled(True)
        n_lef = len(self._lef_paths)
        self._sb_label.setText(
            f"Loaded: {os.path.basename(json_f)}  |  {n_lef} LEF file(s) found — click ▶ Run STA"
        )

    def _set_files_from_args(self, json_f, top, sdc_f, def_f):
        self._json_f    = json_f
        self._sdc_f     = sdc_f
        self._def_f     = def_f
        self._top       = top
        self._lef_paths = self._find_lefs_near(def_f)
        self._act_run.setEnabled(True)
        n_lef = len(self._lef_paths)
        self._sb_label.setText(
            f"CLI: {os.path.basename(json_f)}  |  {n_lef} LEF file(s) — click ▶ Run STA"
        )

    # ── STA execution ─────────────────────────────────────────────────────────

    def _run_sta(self):
        self._act_run.setEnabled(False)
        self._act_load.setEnabled(False)
        self._sb_label.setText("Starting STA…")

        self._worker = STAWorker(
            self._json_f, self._top, self._sdc_f, self._def_f,
            self._use_net_delay, self._lef_paths,
        )
        self._worker.sig_progress.connect(self._sb_label.setText)
        self._worker.sig_finished.connect(self._on_sta_done)
        self._worker.sig_error.connect(self._on_sta_error)
        self._worker.start()

    def _on_sta_done(self, tg, die, comps, nets, port_pos, pin_wl, lef_sizes):
        self._tg         = tg
        self._components = comps
        self._lef_sizes  = lef_sizes
        self._act_run.setEnabled(True)
        self._act_load.setEnabled(True)

        # WNS: only real endpoints (no fanout, slack computed)
        slacks = [n.end_point_slack for n in tg.nodes.values()
                  if len(n.fanout) == 0 and n.end_point_slack < 1e17]
        self._wns = min(slacks) if slacks else 0.0

        self._draw_layout(die, comps, port_pos, tg, lef_sizes)
        self._draw_all_nets(nets, comps, port_pos, lef_sizes)
        self._draw_timing_paths(tg, comps, lef_sizes)
        self._fit_view()

        n_neg = sum(1 for s in slacks if s < 0)
        self._sb_label.setText(
            f"STA complete — {len(comps)} cells | "
            f"{n_neg} violations | WNS={self._wns:.2f} ps | "
            f"Net delay: {'ON' if self._use_net_delay else 'OFF (ideal)'}"
        )

    def _on_sta_error(self, msg):
        self._act_run.setEnabled(True)
        self._act_load.setEnabled(True)
        QMessageBox.critical(self, "STA Error", msg[:2000])
        self._sb_label.setText("STA failed — see error dialog.")

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _def_to_scene(self, x, y):
        """DEF coordinates (y up) → scene coordinates (y down)."""
        return x, -y

    def _cell_size(self, cell_type, lef_sizes):
        return lef_sizes.get(cell_type, (CELL_W_DEFAULT, CELL_H_DEFAULT))

    def _cell_center(self, comp, lef_sizes):
        w, h = self._cell_size(comp['type'], lef_sizes)
        return comp['x'] + w // 2, comp['y'] + h // 2

    def _draw_layout(self, die_area, components, port_pos, tg, lef_sizes):
        self._scene.clear()
        self._scene.cell_items.clear()
        self._scene.path_items.clear()
        self._scene.store_net_items([])

        # --- Die boundary ---
        if die_area and len(die_area) >= 2:
            xs = [p[0] for p in die_area]
            ys = [p[1] for p in die_area]
            sx, sy = self._def_to_scene(min(xs), max(ys))
            self._scene.addRect(
                sx, sy,
                max(xs) - min(xs), max(ys) - min(ys),
                QPen(_C_DIE_EDGE, 5),
                QBrush(_C_DIE_FILL),
            ).setZValue(0)

        # --- Cells (default blue; colored after paths are drawn) ---
        for inst_name, comp in components.items():
            w, h = self._cell_size(comp['type'], lef_sizes)
            sx, sy = self._def_to_scene(comp['x'], comp['y'] + h)
            ci = CellItem(inst_name, comp['type'], sx, sy, w, h, self._scene)
            self._scene.addItem(ci)
            self._scene.cell_items[inst_name] = ci

        # --- Primary I/O ports ---
        dot_r = CELL_H_DEFAULT // 2
        for port_name, (px, py) in port_pos.items():
            sx, sy = self._def_to_scene(px, py)
            dot = self._scene.addEllipse(
                sx - dot_r, sy - dot_r, dot_r * 2, dot_r * 2,
                QPen(_C_PORT, 2),
                QBrush(_C_PORT),
            )
            dot.setZValue(2)
            dot.setToolTip(f"PORT: {port_name}")

    def _draw_all_nets(self, nets, components, port_pos, lef_sizes):
        """Draw all net connections as thin gray lines (initially hidden)."""
        net_items = []
        pen = QPen(_C_NET_LINES, 2, Qt.SolidLine)

        def _center(inst, pin):
            if inst == 'PIN':
                return port_pos.get(pin)
            c = components.get(inst)
            if c is None:
                return None
            cx, cy = self._cell_center(c, lef_sizes)
            return cx, cy

        for net_name, conns in nets.items():
            driver_pos = None
            for inst, pin in conns:
                p = _center(inst, pin)
                if p:
                    driver_pos = p
                    break
            if driver_pos is None:
                continue

            dx, dy = self._def_to_scene(*driver_pos)
            for inst, pin in conns:
                lp = _center(inst, pin)
                if lp is None:
                    continue
                lx, ly = self._def_to_scene(*lp)
                if (lx, ly) == (dx, dy):
                    continue
                li = self._scene.addLine(dx, dy, lx, ly, pen)
                li.setZValue(1)
                li.setVisible(False)  # hidden by default
                net_items.append(li)

        self._scene.store_net_items(net_items)

    def _draw_timing_paths(self, tg, components, lef_sizes):
        """Trace and draw up to 100 worst timing paths, then color cells on those paths."""
        endpoints = sorted(
            [n for n in tg.nodes.values()
             if len(n.fanout) == 0 and n.end_point_slack < 1e17],
            key=lambda n: n.end_point_slack,
        )

        # inst -> worst slack of any DRAWN path containing it
        path_inst_slack = {}

        MAX_PATHS = 100
        for ep in endpoints[:MAX_PATHS]:
            inst_seq = self._trace_path(ep)
            points = []
            for inst in inst_seq:
                c = components.get(inst)
                if c:
                    cx, cy = self._cell_center(c, lef_sizes)
                    sx, sy = self._def_to_scene(cx, cy)
                    points.append(QPointF(sx, sy))

            if len(points) < 2:
                continue

            pi = TimingPathItem(points, ep.end_point_slack, self._wns,
                                inst_seq, self._scene)
            self._scene.addItem(pi)
            self._scene.path_items.append(pi)

            # Track worst slack per instance across drawn paths
            for inst in inst_seq:
                if inst not in path_inst_slack or ep.end_point_slack < path_inst_slack[inst]:
                    path_inst_slack[inst] = ep.end_point_slack

        # Color only cells that appear in at least one drawn path
        for inst, slack in path_inst_slack.items():
            ci = self._scene.cell_items.get(inst)
            if ci:
                ci.set_slack_color(slack, self._wns)

    def _trace_path(self, endpoint):
        """Walk worst_pred_arc backwards from endpoint; return inst list."""
        seq = []
        cur = endpoint
        visited = set()
        while cur is not None:
            uid = id(cur)
            if uid in visited:
                break
            visited.add(uid)
            seq.append(cur.inst)
            arc = cur.worst_pred_arc
            cur = arc.src if arc else None
        seq.reverse()
        return seq

    # ── UI callbacks ──────────────────────────────────────────────────────────

    def _toggle_net_delay(self, checked):
        self._use_net_delay = checked
        self._act_net_delay.setText(f"Net Delay: {'ON' if checked else 'OFF (ideal)'}")
        if self._tg:  # re-run STA with new setting
            self._run_sta()

    def _toggle_paths(self, checked):
        self._act_show_paths.setText(f"Paths: {'ON' if checked else 'OFF'}")
        self._scene.set_paths_visible(checked)

    def _toggle_nets(self, checked):
        self._act_show_nets.setText(f"All Nets: {'ON' if checked else 'OFF'}")
        self._scene.set_nets_visible(checked)

    def _fit_view(self):
        rect = self._scene.itemsBoundingRect()
        if not rect.isNull():
            self._view.fitInView(rect, Qt.KeepAspectRatio)

    def _on_cell_clicked(self, item: CellItem):
        if self._tg:
            self._detail.show_cell(item, self._tg.nodes)

    def _on_path_clicked(self, item: TimingPathItem):
        if self._tg:
            self._detail.show_path(item, self._tg.nodes)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Easy_STA")

    win = MainWindow()

    # CLI pre-load:
    #   python gui_viewer.py netlist.json TOP sdc.sdc layout.def
    #   python gui_viewer.py netlist.json sdc.sdc layout.def   (auto-detect module)
    def _autodetect_top(json_f):
        import json as _json
        try:
            mods = list(_json.load(open(json_f)).get("modules", {}).keys())
            return mods[0] if mods else ""
        except Exception:
            return ""

    if len(sys.argv) == 5:
        win._set_files_from_args(
            json_f=sys.argv[1], top=sys.argv[2],
            sdc_f=sys.argv[3],  def_f=sys.argv[4],
        )
    elif len(sys.argv) == 4:
        top = _autodetect_top(sys.argv[1])
        win._set_files_from_args(
            json_f=sys.argv[1], top=top,
            sdc_f=sys.argv[2],  def_f=sys.argv[3],
        )

    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
