"""Print every skipped test (with its source-level reason) and per-module totals.

Reads the surefire XML reports after the Travis build. Surefire records no message for a
bare @Ignore, so for each skipped test the reason is looked up in the test source: the
@Ignore/@Disabled line on the method (or class) plus the comment lines directly above it.
Python 3.4 compatible (Travis trusty image).
"""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

ANNOT = re.compile(r'@(Ignore|Disabled)\b.*')


def find_source(classname):
    rel = os.path.join('src', 'test', 'java', *classname.split('$')[0].split('.')) + '.java'
    for d in sorted(walk_dirs()):
        cand = os.path.join(d, rel)
        if os.path.isfile(cand):
            return cand
    return None


def walk_dirs():
    # Python 3.4 has no recursive glob; module roots are the dirs holding a pom.xml
    for dirpath, dirnames, filenames in os.walk('.'):
        dirnames[:] = [n for n in dirnames if n not in ('target', '.git', 'node_modules')]
        if 'pom.xml' in filenames:
            yield dirpath


def find_reports():
    out = []
    for d in walk_dirs():
        out.extend(glob.glob(os.path.join(d, 'target', 'surefire-reports', 'TEST-*.xml')))
    return sorted(out)


def reason_from_source(path, method):
    if not path:
        return 'source not found'
    with open(path) as fh:
        lines = fh.read().splitlines()
    decl = re.compile(r'\bvoid\s+' + re.escape(method) + r'\s*\(')
    for i, line in enumerate(lines):
        if decl.search(line):
            return scan_up(lines, i) or class_reason(lines) or 'skipped (no annotation found)'
    return class_reason(lines) or 'skipped (method not found in source)'


def scan_up(lines, idx):
    j = idx - 1
    while j >= 0 and lines[j].strip() and not lines[j].strip().endswith(('}', ';')):
        m = ANNOT.search(lines[j])
        if m:
            comments = []
            k = j - 1
            while k >= 0 and lines[k].strip().startswith(('//', '*', '/*', '@')):
                if not lines[k].strip().startswith('@'):
                    comments.insert(0, lines[k].strip())
                k -= 1
            return m.group(0).strip() + (' -- ' + ' '.join(comments) if comments else '')
        j -= 1
    return None


def class_reason(lines):
    for i, line in enumerate(lines):
        if re.search(r'\bclass\s+\w+', line):
            r = scan_up(lines, i)
            return ('class-level ' + r) if r else None
    return None


def main():
    reports = find_reports()
    print('=== Skipped tests (surefire <skipped> entries, reason from test source) ===')
    totals = {}
    for p in reports:
        module = p.split('/target/')[0]
        root = ET.parse(p).getroot()
        agg = totals.setdefault(module, [0, 0, 0, 0])
        agg[0] += int(root.get('tests', 0))
        agg[1] += int(root.get('failures', 0))
        agg[2] += int(root.get('errors', 0))
        agg[3] += int(root.get('skipped', 0))
        for tc in root.iter('testcase'):
            s = tc.find('skipped')
            if s is None:
                continue
            cls = tc.get('classname') or ''
            name = tc.get('name') or ''
            msg = s.get('message')
            src = reason_from_source(find_source(cls), name)
            print('SKIPPED %s.%s: %s%s' % (cls, name, src, (' [surefire message: %s]' % msg) if msg else ''))
    print('=== Test totals per module (surefire XML) ===')
    gt = [0, 0, 0, 0]
    for module in sorted(totals):
        t, f, e, s = totals[module]
        gt = [a + b for a, b in zip(gt, totals[module])]
        print('%s: tests=%d failures=%d errors=%d skipped=%d passed=%d' % (module, t, f, e, s, t - f - e - s))
    t, f, e, s = gt
    print('TOTAL: tests=%d failures=%d errors=%d skipped=%d passed=%d' % (t, f, e, s, t - f - e - s))
    return 0


if __name__ == '__main__':
    sys.exit(main())
