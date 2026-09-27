"""Fingerprint actual source and numerical dependencies without exporting secrets."""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import subprocess
import numpy as np
from .validation import sha256_file


def implementation_manifest():
    package = Path(__file__).resolve().parent
    root = package.parent
    files = {'cranio/'+p.relative_to(package).as_posix(): sha256_file(p) for p in sorted(package.rglob('*.py'))}
    for name in ('gnm_reconstruct.py', 'addon_v13.py'):
        if (root/name).exists():
            files[name] = sha256_file(root/name)
    if root.name == 'gnm_cranio' and (root/'__init__.py').exists():
        files['addon_v13.py'] = sha256_file(root/'__init__.py')
    canonical = '\n'.join(name+':'+digest for name, digest in sorted(files.items()))
    result = dict(source_sha256=hashlib.sha256(canonical.encode()).hexdigest(), files=files, git_commit=None, git_dirty=None)
    if (root/'.git').exists():
        try:
            result['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL, timeout=2).strip()
            result['git_dirty'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True, stderr=subprocess.DEVNULL, timeout=2).strip())
        except (OSError, subprocess.SubprocessError):
            pass
    return result


def numerical_environment():
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        np.show_config()
    return dict(numpy_build=stream.getvalue(), thread_environment={key: os.environ.get(key)
        for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'BLIS_NUM_THREADS')})
