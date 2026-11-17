"""Shared fail-closed destination checks and staged report publication."""
import os
from pathlib import Path, PureWindowsPath
import tempfile

from .inputs import InputError
from .suite import paths_alias


def check_outputs(paths, protected, force):
    for index, path in enumerate(paths):
        if os.name == 'nt':
            for part in path.parts:
                if part == path.anchor or part in ('.', '..'):
                    continue
                if part.endswith(('.', ' ')) or ':' in part or PureWindowsPath(part).is_reserved():
                    raise InputError('Ambiguous or reserved Windows output path component')
        if any(paths_alias(path, source) for source in protected):
            raise InputError('Output would overwrite an input database, sidecar or case file')
        if any(paths_alias(path, other) for other in paths[:index]):
            raise InputError('JSON and HTML outputs must be distinct files')
        if not path.parent.is_dir():
            raise InputError('Output parent directory does not exist')
        if path.is_symlink():
            raise InputError('Refusing a symbolic-link output')
        if path.exists() and (not force or not path.is_file()):
            raise InputError('Output exists; use --force only for an ordinary report file')


def write_outputs(outputs, force):
    """Stage all text first. Multi-file publication is not transactional."""
    staged = []
    try:
        for destination, text in outputs:
            handle, name = tempfile.mkstemp(prefix='.planbench-', suffix='.tmp', dir=destination.parent)
            temporary = Path(name)
            staged.append((temporary, destination))
            with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as stream:
                stream.write(text)
        for temporary, destination in staged:
            if force:
                os.replace(temporary, destination)
            else:
                os.link(temporary, destination)
                temporary.unlink()
    finally:
        for temporary, destination in staged:
            temporary.unlink(missing_ok=True)
