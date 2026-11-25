"""Spacebar pans while a sidebar control has keyboard focus."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from PySide6.QtCore import Qt,QPoint,QRectF
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QWidget,QHBoxLayout,QSpinBox,QGraphicsScene
from PySide6.QtTest import QTest
from gui.pages.map import MapView

class SpacePanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
    def test_sidebar_focus_and_pointer_over_map(self):
        page=SimpleNamespace(cursor_for_tool=lambda:Qt.CrossCursor,press=Mock(return_value=True),
                             move=Mock(),release=Mock(),minimap=Mock(),overlay=Mock(),key=Mock(return_value=False))
        window=QWidget();layout=QHBoxLayout(window);view=MapView(page);spin=QSpinBox()
        layout.addWidget(view);layout.addWidget(spin)
        scene=QGraphicsScene(view);scene.setSceneRect(QRectF(0,0,2000,2000));view.setScene(scene)
        window.resize(640,400);window.show();window.activateWindow();self.app.processEvents()
        QCursor.setPos(view.viewport().mapToGlobal(QPoint(100,100)));spin.setFocus();self.app.processEvents()
        before=view.horizontalScrollBar().value()
        QTest.keyPress(spin,Qt.Key_Space)
        self.assertTrue(view.space)
        QTest.mousePress(view.viewport(),Qt.LeftButton,pos=QPoint(100,100))
        QTest.mouseMove(view.viewport(),QPoint(140,100))
        QTest.mouseRelease(view.viewport(),Qt.LeftButton,pos=QPoint(140,100))
        self.assertNotEqual(before,view.horizontalScrollBar().value())
        page.press.assert_not_called();page.release.assert_not_called()
        QTest.keyRelease(view,Qt.Key_Space);self.assertFalse(view.space)
        # Space over the sidebar must keep normal control behavior.
        QCursor.setPos(spin.mapToGlobal(spin.rect().center()));spin.setFocus()
        QTest.keyPress(spin,Qt.Key_Space);self.assertFalse(view.space)
        QTest.keyRelease(spin,Qt.Key_Space)
        window.close();window.deleteLater();self.app.processEvents()
