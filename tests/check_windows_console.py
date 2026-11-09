"""Check the live Windows proxy and descendants for visible consoles; no cloud calls."""
import argparse
import os


def check(root):
    if os.name != "nt":
        raise OSError("This process/console check is Windows-only.")
    import ctypes
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)

    class Entry(ctypes.Structure):
        _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("pid", w.DWORD),
                    ("heap", ctypes.c_size_t), ("module", w.DWORD), ("threads", w.DWORD),
                    ("parent", w.DWORD), ("priority", w.LONG), ("flags", w.DWORD), ("name", w.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = w.HANDLE
    kernel.Process32FirstW.argtypes = [w.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.AttachConsole.argtypes = [w.DWORD]
    kernel.GetConsoleWindow.restype = w.HWND
    user.IsWindowVisible.argtypes = [w.HWND]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    processes = {}
    try:
        row = Entry()
        row.size = ctypes.sizeof(row)
        present = kernel.Process32FirstW(snapshot, ctypes.byref(row))
        while present:
            processes[row.pid] = (row.parent, row.name)
            present = kernel.Process32NextW(snapshot, ctypes.byref(row))
    finally:
        kernel.CloseHandle(snapshot)
    if root not in processes:
        raise OSError("The supplied proxy PID is no longer running.")
    children = {root}
    while True:
        new = {pid for pid, (parent, _) in processes.items() if parent in children} - children
        if not new:
            break
        children |= new
    visible = []
    for pid in sorted(children):
        # Detach this short-lived checker, never the target process. AttachConsole
        # observes a target console even when conhost owns its top-level window.
        kernel.FreeConsole()
        try:
            attached = kernel.AttachConsole(pid)
            window = kernel.GetConsoleWindow() if attached else None
            if window and user.IsWindowVisible(window):
                visible.append((pid, processes[pid][1]))
        finally:
            kernel.FreeConsole()
    if visible:
        raise RuntimeError(f"Visible proxy console(s): {visible}")
    print(f"PASS: proxy and all {len(children) - 1} descendant processes have no visible console")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True, help="Verified live proxy PID from argon.pid")
    args = parser.parse_args()
    try:
        check(args.pid)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"FAIL: {error}\n")
