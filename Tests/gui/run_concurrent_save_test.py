#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ***** BEGIN LICENSE BLOCK *****
# This file is part of Natron <https://natrongithub.github.io/>,
# (C) 2018-2023 The Natron developers
#
# Natron is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Natron is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Natron.  If not, see <http://www.gnu.org/licenses/gpl-2.0.html>
# ***** END LICENSE BLOCK *****

"""Headless test of projects saved by several Natron processes at the same time.

Usage: run_concurrent_save_test.py /path/to/NatronRenderer

Several NatronRenderer processes start together, and each one saves its own project many
times. Each project holds one node whose script name identifies the process. Every saved file
must be a project that holds the node of the process that saved it, and no other.

The project was first written to a temporary file named after the time in milliseconds only,
shared by all processes: two saves in the same millisecond wrote the same file, so that a
project was saved with the content of the project of another process, or the save failed
("Failed to save to ...") and left an empty project file.

Exit status: 0 on success, 1 on failure.
"""

import os
import subprocess
import sys
import tempfile

PROCESSES = 8
SAVES = 150
TIMEOUT = 240  # seconds

SCRIPT = """
import os, sys, time
from NatronEngine import natron
OUT = os.environ["NATRON_SAVE_TEST_DIR"]
INDEX = os.environ["NATRON_SAVE_TEST_INDEX"]
node = app.createNode("fr.inria.built-in.BackDrop")
node.setScriptName("marker_p" + INDEX + "_end")
# all processes start to save at the same time
start = os.path.join(OUT, "start")
while not os.path.exists(start):
    time.sleep(0.005)
status = 0
for k in range(int(os.environ["NATRON_SAVE_TEST_SAVES"])):
    path = os.path.join(OUT, "p%s_%04d.ntp" % (INDEX, k)).replace("\\\\", "/")
    try:
        app.saveProjectAs(path)
    except BaseException as e:
        sys.stdout.write("SAVE_RAISED %s: %r\\n" % (path, e))
        status = 1
sys.stdout.write("SAVES_DONE\\n"); sys.stdout.flush()
natron.quit(status)
"""


def main():
    if len(sys.argv) != 2:
        sys.stderr.write(__doc__)
        return 1
    renderer = sys.argv[1]
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "script.py")
        with open(script, "w") as f:
            f.write(SCRIPT)
        procs = []
        for i in range(PROCESSES):
            env = dict(os.environ, NATRON_SAVE_TEST_DIR=tmp, NATRON_SAVE_TEST_INDEX=str(i),
                       NATRON_SAVE_TEST_SAVES=str(SAVES))
            log = open(os.path.join(tmp, "log%d.txt" % i), "wb")
            procs.append((subprocess.Popen([renderer, script], stdin=subprocess.DEVNULL, stdout=log,
                                           stderr=subprocess.STDOUT, env=env), log))
        # let every process reach its wait loop, then release them together
        import time
        time.sleep(15)
        open(os.path.join(tmp, "start"), "w").close()
        for i, (p, log) in enumerate(procs):
            try:
                p.wait(TIMEOUT)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
                errors.append("process %d did not exit after %d s" % (i, TIMEOUT))
            log.close()
            with open(os.path.join(tmp, "log%d.txt" % i), errors="replace") as f:
                output = f.read()
            if "SAVES_DONE" not in output:
                errors.append("process %d did not finish its saves:\n%s" % (i, output[-1500:]))
            for line in output.splitlines():
                if "Failed to save" in line or "SAVE_RAISED" in line:
                    errors.append("process %d: %s" % (i, line))

        for i in range(PROCESSES):
            own = ("marker_p%d_end" % i).encode()
            for k in range(SAVES):
                name = "p%d_%04d.ntp" % (i, k)
                try:
                    with open(os.path.join(tmp, name), "rb") as f:
                        data = f.read()
                except OSError:
                    errors.append("%s: missing" % name)
                    continue
                if not data:
                    errors.append("%s: empty file" % name)
                    continue
                others = [j for j in range(PROCESSES) if j != i and ("marker_p%d_end" % j).encode() in data]
                if own not in data or others:
                    errors.append("%s: holds the project of process %s, not its own" % (name, others or "?"))

    if errors:
        sys.stdout.write("FAIL: %d errors, the first ones:\n" % len(errors))
        for e in errors[:12]:
            sys.stdout.write("  " + e + "\n")
        return 1
    sys.stdout.write("OK: %d processes x %d saves\n" % (PROCESSES, SAVES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
