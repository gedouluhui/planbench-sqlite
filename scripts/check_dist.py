"""Validate actual sdist public documents and their relative Markdown links."""
import posixpath
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
from urllib.parse import unquote, urlsplit

REQUIRED = {'README.md', 'README.zh-CN.md', 'LICENSE', 'CONTRIBUTING.md', 'CHANGELOG.md',
            'docs/CONTRACT.md', 'docs/index.html', 'docs/different.html', 'docs/limited.html'}


def check_archive(path):
    with tarfile.open(path, 'r:gz') as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1:
            raise ValueError('Archive must have one source root')
        root = roots.pop()
        files = {member.name[len(root) + 1:]: member for member in members}
        missing = REQUIRED - files.keys()
        if missing:
            raise ValueError('Missing public files: ' + ', '.join(sorted(missing)))
        if any('.local' in PurePosixPath(name).parts or name.startswith('docs/superpowers/') for name in files):
            raise ValueError('Private working material present in sdist')
        links = 0
        for name, member in files.items():
            if not name.endswith('.md'):
                continue
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError('Cannot read document member')
            text = stream.read().decode('utf-8')
            for target in re.findall(r'\[[^\]]*\]\(([^)\s]+)\)', text):
                url = urlsplit(target)
                if url.scheme or url.netloc or not url.path:
                    continue
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path)))
                if resolved not in files:
                    raise ValueError(f'Broken relative link in {name}: {target}')
                links += 1
        return len(files), links


if __name__ == '__main__':
    candidates = [Path(value) for value in sys.argv[1:]] or list(Path('dist').glob('*.tar.gz'))
    if not candidates:
        raise SystemExit('No source archive supplied or found')
    try:
        for candidate in candidates:
            count, links = check_archive(candidate)
            print(f'{candidate.name}: {count} files; {links} relative document links verified')
    except (ValueError, OSError, tarfile.TarError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
