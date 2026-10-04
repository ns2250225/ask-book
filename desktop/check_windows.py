"""Verify release EXE/sidecar use the GUI subsystem and ship as one file."""
from pathlib import Path
import struct
import sys


def gui_executable(path):
    data = path.read_bytes()
    assert data[:2] == b'MZ', f'{path}: missing DOS header'
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    assert data[pe:pe+4] == b'PE\0\0', f'{path}: missing PE header'
    # Subsystem has the same offset in PE32 and PE32+ optional headers.
    subsystem = struct.unpack_from('<H', data, pe+4+20+68)[0]
    assert subsystem == 2, f'{path}: subsystem {subsystem}, expected Windows GUI (2)'
    return data


if __name__ == '__main__':
    root = Path(__file__).resolve().parent.parent
    host = gui_executable(Path(sys.argv[1]))
    sidecar = gui_executable(root / 'src-tauri/binaries/bookskill-sidecar.exe')
    assert sidecar in host, 'Python sidecar is not embedded in the portable EXE'
    print('Windows GUI subsystem and embedded sidecar verified')
