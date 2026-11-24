"""หน้าต่างใบความรู้อุปกรณ์: รายการตามหมวด + เนื้อหา + Export รวมเล่ม PDF/HTML."""
from __future__ import annotations

from ..i18n import tr

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QPushButton, QSplitter, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout,
)

from ..panel.catalog import CATALOG, CATEGORIES
from ..panel.knowledge import ANNOTATION, handbook_html, sheet_html
from . import theme

CSS = (f"<style>body{{color:{theme.TEXT};}} h2{{color:{theme.ACCENT};}} h3{{color:#22D3EE; margin-top:14px;}}"
       f"table{{border-color:{theme.GRID_MAJOR};}} th{{background:{theme.BG_PANEL_DARK};}}</style>")


def export_pdf(path, html: str) -> None:
    doc = QTextDocument()
    doc.setHtml(html)
    pdf = QPdfWriter(str(path))
    pdf.setPageSize(QPageSize(QPageSize.A4))
    pdf.setResolution(120)
    doc.print_(pdf)


class KnowledgeDialog(QDialog):
    def __init__(self, parent=None, kind: str | None = None, props: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle(tr("📘 ใบความรู้อุปกรณ์"))
        self.resize(1080, 760)
        self.props = props
        self.kind = None
        self._props_kind = None
        v = QVBoxLayout(self)
        sp = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumWidth(330)
        self._items = {}
        for cat, name in CATEGORIES:
            kinds = [k for k, i in CATALOG.items() if i.category == cat and k not in ANNOTATION]
            if not kinds:
                continue
            top = QTreeWidgetItem([name])
            top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
            for k in kinds:
                it = QTreeWidgetItem([CATALOG[k].name])
                it.setData(0, Qt.UserRole, k)
                top.addChild(it)
                self._items[k] = it
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self.tree.currentItemChanged.connect(lambda it, _p: it and it.data(0, Qt.UserRole) and
                                             self.show_kind(it.data(0, Qt.UserRole)))
        self.view = QTextBrowser()
        sp.addWidget(self.tree)
        sp.addWidget(self.view)
        sp.setSizes([300, 780])
        v.addWidget(sp, 1)
        h = QHBoxLayout()
        b_one = QPushButton(tr("📄 PDF หน้านี้"))
        b_all = QPushButton(tr("📚 PDF รวมเล่มทุกอุปกรณ์"))
        b_html = QPushButton(tr("🌐 HTML รวมเล่ม"))
        b_close = QPushButton(tr("ปิด"))
        b_one.clicked.connect(lambda: self.export("one"))
        b_all.clicked.connect(lambda: self.export("all"))
        b_html.clicked.connect(lambda: self.export("html"))
        b_close.clicked.connect(self.close)
        h.addStretch(1)
        for b in (b_one, b_all, b_html, b_close):
            h.addWidget(b)
        v.addLayout(h)
        first = kind if kind in self._items else "pushbutton"
        self._props_kind = kind
        self.tree.setCurrentItem(self._items[first])
        self.show_kind(first)

    def show_kind(self, kind: str, props: dict | None = None):
        self.kind = kind
        self.view.setHtml(CSS + sheet_html(kind, self._props_for(kind)))

    def _props_for(self, kind):
        """ค่าจริงของอุปกรณ์ที่เลือกบนผัง ใช้เฉพาะกับชนิดเดียวกัน."""
        return self.props if kind == self._props_kind else None

    def export(self, what: str, path: str | None = None) -> str | None:
        ext = "html" if what == "html" else "pdf"
        name = tr("ใบความรู้_{0}", CATALOG[self.kind].name.split(' ')[0]) if what == "one" else tr("ใบความรู้อุปกรณ์_รวมเล่ม")
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("Export ใบความรู้"), f"{name}.{ext}",
                                                  "PDF (*.pdf)" if ext == "pdf" else "HTML (*.html)")
        if not path:
            return None
        if what == "html":
            Path(path).write_text(handbook_html(), encoding="utf-8")
        elif what == "all":
            export_pdf(path, handbook_html())
        else:
            export_pdf(path, f"<html><body>{sheet_html(self.kind, self._props_for(self.kind))}</body></html>")
        return path
