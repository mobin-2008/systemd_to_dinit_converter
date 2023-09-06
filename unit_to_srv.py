#!/usr/bin/python3
### unit_to_srv.py: Convert systemd unit files into dinit services
#
# Requires Python 3.10 or later!
#
# SPDX-License-Identifier: ISC
#
# Copyright (C) 2023 Mobin Aydinfar
#
# Permission to use, copy, modify, and /or distribute this software for any purpose
# with or without fee is hereby granted, provided that the above copyright notice and
# this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD
# TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS.
# IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
# DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION
# ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

import os
import argparse

## Systemd unit "key" ref map
systemd_ref_map = [
    "Description",
    # We map systemd things in this order:
    "Type", # simple -> process (bgprocess?)
            # exec -> process
            # forking -> bgprocess
            # oneshot -> scripted
            # notify -> process
    "Wants", # -> waits-for
    "Requires", # -> depends-on
    "Requisite", # -> depends-on
    "BindsTo", # -> depends-on
    "PartOf", # -> depends-on
    "Upholds", # -> waits-for
    "Before", # -> before
    "After", # -> after
    "OnSuccess", # -> chain-to
    "StartLimitBurst", # -> restart-limit-count
    "StartLimitIntervalSec", # -> restart-limit-interval
    "Alias", # -> an another service with depends-on this service
    "WantedBy", # -> depends-ms
    "RequiredBy", # -> depends-ms
    "UpheldBy", # -> depends-ms
    "PIDFile", # -> pid-file
    "ExecStart", # -> command
    "ExecStop", # -> stop-command
    "TimeoutStartSec", # -> start-timeout # Give warning on werid values
    "TimeoutStopSec", # -> stop-timeout # Same
    "TimeoutSec", # -> both: start-timeout, stop-timeout
    "Restart", # -> restart (with converting some systemd things)
    "EnvironmentFile", # -> env-file
    "User", # -> run-as = User:
    "Group", # -> run-as =    :Group
    "WorkingDirectory", # -> working-dir
    "LimitCORE", # -> rlimit-core
    "LimitDATA", # -> rlimit-data
    "LimitNOFILE", # -> rlimit-nofile
    "UtmpIdentifier", # -> inittab-line
    "KillSignal", # -> term-signal
]

## Empty list for comments
comments = [ ]

## Empty list for values
values = [ ]

def warning(message):
    if args.quiet:
        print(f'\nWARN: {message}\n')

# Systemd has a basic syntax for times, such as (5min and 20sec) but
# we need to convert them into seconds only.
def parse_time(time):
    if time.isnumeric():
        return time
    SEC = 0
    MEM = ""
    WHAT = ""
    LETTER = False
    TIMES = [ ]
    for ch in time:
        # Sadly, systemd doesn't require spaces between different time types
        # So, We need to advanced parsing. Meh
        # Store systemd times as a list into TIMES list
        if ch == " ":
            continue # Skip empty spaces
        if ch.isnumeric():
            if not LETTER:
                MEM += ch
                continue
            else:
                TIMES.append([ WHAT.strip(), MEM.strip() ])
                MEM += ch # Here's Next entry
                WHAT = "" # Reset WHAT for new entry
                LETTER = False # Reset LETTER for new entry
                continue
        if ch.isalpha():
            WHAT += ch
            LETTER = True
    TIMES.append([ WHAT.strip(), MEM.strip() ]) # Catch last entry
    for item in TIMES:
        match item[0]:
            case "μs" | "us" | "usec":
                SEC += (float(MEM) / 1000000)
            case "ms" | "msec":
                SEC += (float(MEM) / 1000)
            case "s" | "sec" | "second" | "seconds":
                SEC += float(MEM)
            case "m" | "min" | "minute" | "minutes":
                SEC += (float(MEM) * 60)
            case "h" | "hr" | "hour" | "hours":
                SEC += (float(MEM) * 3600)
            case "d" | "day" | "days":
                SEC += (float(MEM) * 86400)
            case "w" | "week" | "weeks":
                SEC += (float(MEM) * 604800)
            case "M" | "month" | "months":
                SEC += (float(MEM) * 2.628e+6)
            case "y" | "year" | "years":
                SEC += (float(MEM) * 3.154e+7)
            case _:
                warning(f"Can't parse given time: {item[0]}: {item[1]}")
    return SEC

## Parse flags
parser = argparse.ArgumentParser(
        prog='unit_to_srv',
        description='Convert systemd unit files into dinit services',
        epilog='See Usage.md for more information'
)
parser.add_argument('unitfile')
parser.add_argument('--quiet', '-q', action='store_false')
args = parser.parse_args()

## Parse systemd unit
# In this stage, We just parse given unit file into a key "map"
with open(args.unitfile, "r", encoding="UTF-8") as file:
    for line in file:
        NAME = ""
        MEMORY= ""
        if line[0] == "#" or line[0] == ";":
            comments.append(f'In systemd service unit comment: {line}') # comment
        elif line[0] != "[":
            for ch in line:
                if ch == "=":
                    NAME = MEMORY
                    MEMORY = ""
                else:
                    MEMORY += ch
            if NAME != "": # Ignore empty lines
                values.append([ NAME.strip(), MEMORY.strip() ])

## Actual converting
## there is where fun begins :)
# Systemd can watch his children syscalls to determine pid in "forking" type
# services, but dinit doesn't support this way (and I think it's just OVER-ENGINERING),
# You shuold provide a pid-file for forking (bgprocess) services.
# 0: Isn't bgprocess, 1: Is bgprocess but doesn't have pid-file, 2: correct bgprocess
IS_PIDFILE = 0
# Some systemd services doesn't have type
HAS_TYPE = False
with open(args.unitfile + '.dinit', "w", encoding="UTF-8") as target:
    for val in values:
        if not val[0] in systemd_ref_map:
            warning(f'Unknown/Unsupported key: {val[0]}')
            continue
        match val[0]:
            case "Description":
                target.write(f'# Description: {val[1]}\n')
            case "Type":
                match val[1]:
                    case "simple" | "exec":
                        target.write('type = process\n')
                    case "forking":
                        target.write('type = bgprocess\n')
                        IS_PIDFILE = 1
                    case "oneshot":
                        target.write('type = scripted\n')
                    case "notify":
                        target.write('type = process\n')
                        warning('''This service use systemd activition protocol
Please change your service to use a proper ready notification protocol:
https://skarnet.org/software/s6/notifywhenup.html''')
                    case "dbus":
                        print('\'type=dbus\' isn\'t supported by dinit!')
                        os._exit(1)
                HAS_TYPE = True
            case "ExecStart":
                target.write(f'command = {val[1]}\n')
            case "ExecStop":
                target.write(f'stop-command = {val[1]}\n')
            case "Wants" | "UpHolds":
                for dep in val[1].split(" "):
                    target.write(f'waits-for = {dep}\n')
            case "Requires" | "Requisite" | "BindsTo" | "PartOf":
                for dep in val[1].split(" "):
                    target.write(f'depends-on = {dep}\n')
            case "WantedBy" | "RequiredBy" | "UpheldBy":
                for dep in val[1].split(" "):
                    target.write(f'depends-ms = {dep}\n')
            case "Before":
                for dep in val[1].split(" "):
                    target.write(f'before = {dep}\n')
                warning('Before in dinit has different functionality over systemd')
            case "After":
                for dep in val[1].split(" "):
                    target.write(f'after = {dep}\n')
                warning('After in dinit has different functionality over systemd')
            case "Alias":
                for alias in val[1].split(" "):
                    with open(alias, "w", encoding="UTF-8") as temp:
                        temp.write(f'depends-on = {args.unitfile}.dinit\n')
                print('Service unit has \"Alias\", Creating another service for convering that')
            case "OnSuccess":
                for chain in val[1].split(" "):
                    target.write(f'chain-to = {val[1]}\n')
            case "StartLimitBurst":
                target.write(f'restart-limit-count = {val[1]}\n')
            case "StartLimitIntervalSec":
                target.write(f'restart-limit-interval = {parse_time(val[1])}\n')
            case "PIDFile":
                target.write(f'pid-file = {val[1]}\n')
                IS_PIDFILE = 2
            case "EnvironmentFile":
                target.write(f'env-file = {val[1]}\n')
            case "Restart":
                if val[1] == "no":
                    target.write('restart = no')
                else:
                    target.write('restart = yes')
            case "TimeoutStartSec" | "TimeoutStopSec" | "TimeoutSec":
                if val[1] == "infinity":
                    TIME = 0
                else:
                    TIME = parse_time(val[1])
                if val[0] == "TimeoutSec":
                    target.write(f'start-timeout = {TIME}\nstop-timeout = {TIME}\n')
                elif "Start" in val[0]:
                    target.write(f'start-timeout = {TIME}\n')
                else:
                    target.write(f'stop-timeout = {TIME}\n')
            case "User":
                STR=f'{val[1]}'
                for grp in values:
                    if grp[0] == "Group":
                        STR=f'{val[1]}:{grp[1]}'
                target.write(f'run-as = {STR}\n')
            case "Group":
                # no-op, handled in "User"
                continue
            case "WorkingDirectory":
                target.write(f'working-dir = {val[1]}\n')
            case "LimitCORE":
                target.write(f'rlimit-core = {val[1]}\n')
            case "LimitNOFILE":
                target.write(f'rlimit-nofile = {val[1]}\n')
            case "LimitDATA":
                target.write(f'rlimit-data = {val[1]}\n')
            case "UtmpIdentifier":
                target.write(f'inittab-line = {val[1]}\n')
            case "KillSignal":
                SIG = f'{val[1]}'.removeprefix('SIG')
                target.write(f'term-signal = {sig}\n')
            case _:
                print(f'Not implemented key: {val[0]}')
        # ToDo: More
    if not HAS_TYPE:
        target.write('type = process\n') # Default fall-back type
    for comment in comments:
        target.write(comment)
    if IS_PIDFILE == 1:
        warning('Service is "forking" type but doesn\'t have any pid-file!, See Usage.md')
        target.write('# Service is "forking" type but doesn\'t have any pid-file!\n')

print('Converting service unit to dinit service is completed.')
print('It\'s HIGHLY recommended to modify this generated file to fit your needs')
print('Done!')
