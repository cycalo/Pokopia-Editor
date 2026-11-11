"""Pokopia Save Editor (v3) - the window.

  pythonw pokopia_gui.py [SAVE_FOLDER] [--theme dark|light] [--screenshot DIR]

The interface uses PySide6 (py -m pip install PySide6-Essentials). Without it, the previous Tkinter
interface in legacy\\pokopia_gui_tk.py starts instead.
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main():
    try:
        import PySide6  # noqa: F401
    except ImportError:
        import runpy
        try:
            import tkinter.messagebox as mb
            mb.showinfo('Pokopia Save Editor', 'The new interface needs PySide6. Install it with\n\n'
                        '    py -m pip install PySide6-Essentials\n\nStarting the previous interface for now.')
        except Exception:
            pass
        sys.argv[0] = os.path.join(HERE, 'legacy', 'pokopia_gui_tk.py')
        runpy.run_path(sys.argv[0], run_name='__main__')
        return
    from gui.app import main as qt_main
    sys.exit(qt_main())


if __name__ == '__main__':
    main()
