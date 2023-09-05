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
]

## Empty list for comments
comments = [ ]

## Empty list for values
values = [ ]

def warning(message):
    if args.quiet:
        print(f'\nWARN: {message}\n')

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
with open(args.unitfile + '.dinit', "w", encoding="UTF-8") as target:
    if "Type" not in values:
        target.write('type = process\n') # Default fall-back type
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
            case "ExecStart":
                target.write(f'command = {val[1]}\n')
            case "ExecStop":
                target.write(f'stop-command = {val[1]}\n')
            case "Wants" | "UpHolds":
                target.write(f'waits-for = {val[1]}\n')
            case "Requires" | "Requisite" | "BindsTo" | "PartOf":
                target.write(f'depends-on = {val[1]}\n')
            case "WantedBy" | "RequiredBy" | "UpheldBy":
                target.write(f'depends-ms = {val[1]}\n')
            case "Before":
                target.write(f'before = {val[1]}\n')
                warning('Before in dinit has different functionality over systemd')
            case "After":
                target.write(f'after = {val[1]}\n')
                warning('After in dinit has different functionality over systemd')
            case "Alias":
                with open(val[1], "w", encoding="UTF-8") as temp:
                    temp.write(f'depends-on = {args.unitfile}.dinit\n')
                print('Service unit has \"Alias\", Creating another service for convering that')
            case "OnSuccess":
                target.write(f'chain-to = {val[1]}\n')
            case "StartLimitBurst":
                target.write(f'restart-limit-count = {val[1]}\n')
            case "StartLimitIntervalSec":
                target.write(f'restart-limit-interval = {val[1]}\n')
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
                elif val[1].isnumeric():
                    TIME = val[1]
                else:
                    # ToDo
                    TIME = val[1]
                    warning("Systemd special timeout (such as 5min and 20sec) isn't supported-yet")
                if val[0] == "TimeoutSec":
                    target.write(f'start-timeout = {TIME}\nstop-timeout = {TIME}')
                elif "Start" in val[0]:
                    target.write(f'start-timeout = {TIME}\n')
                else:
                    target.write(f'stop-timeout = {TIME}\n')
            case _:
                print(f'Not implemented key: {val[1]}')
        # ToDo: More
    for comment in comments:
        target.write(comment)
    if IS_PIDFILE == 1:
        warning('Service is "forking" type but doesn\'t have any pid-file!, See Usage.md')
        target.write('# Service is "forking" type but doesn\'t have any pid-file!\n')

print('Converting service unit to dinit service is completed.')
print('It\'s HIGHLY recommended to modify this generated file to fit your needs')
print('Done!')
