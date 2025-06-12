#!/usr/bin/python3
### unit_to_srv.py: Convert systemd unit files into dinit services
# Requires Python 3.10 or later!
#
# Useful resources:
# Systemd documention:
#       man:systemd.unit(5)
#       man:systemd.service(5)
#       man:systemd.timer(5)
#       man:systemd.kill(5)
#       man:systemd.exec(5)
#
# Skarnet.org's unit conversion:
#       https://skarnet.org/software/s6/unit-conversion.html
#
# SPDX-License-Identifier: BSD-2-Clause
#
# Copyright (C) 2023-2024 Mobin Aydinfar
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list
#    of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list
#    of conditions and the following disclaimer in the documentation and/or other materials
#    provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS “AS IS” AND ANY EXPRESS
# OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER
# OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
# ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import os
import signal
import argparse
import pathlib
from dataclasses import dataclass

# A C-style structure to keep .ini style files key=value configs
@dataclass
class key_value_struct:
    key: str
    value: str

## Systemd unit "key" reference map
systemd_ref_map = [
    # We ignore these keys:
    "Documentation",
    # We don't provide support for these keys:
    "Group", # -> Dinit doesn't support setting group along with user
    # We map systemd things in this order:
    "Type", # simple -> process
            # exec -> process
            # forking -> bgprocess
            # oneshot -> scripted
            # notify -> process
    "Description", # -> A comment at dinit service
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
    "WantedBy", # -> before
    "RequiredBy", # -> before
    "UpheldBy", # -> before
    "PIDFile", # -> pid-file
    "ExecStart", # -> command
    "ExecStop", # -> stop-command
    "TimeoutStartSec", # -> start-timeout, with converting systemd timespans
    "TimeoutStopSec", # -> stop-timeout, same
    "TimeoutSec", # -> both: start-timeout, stop-timeout
    "Restart", # -> restart (with converting some systemd things)
    "EnvironmentFile", # -> env-file
    "User", # -> run-as = User
    "WorkingDirectory", # -> working-dir
    "LimitCORE", # -> rlimit-core
    "LimitDATA", # -> rlimit-data
    "LimitNOFILE", # -> rlimit-nofile
    "UtmpIdentifier", # -> inittab-line
    "KillSignal", # -> term-signal
]

## List for comments
comments = [ ]

## Map for input file (systemd unit)
input_map = [ ]

## Map for output file (dinit service)
output_map = [ ]

def warning(message):
    if not args.quiet:
        print(f'\nWARN: {message}')

def sub_warning(message, flush):
    if not args.quiet:
        print(f'... {message}')
        if flush:
            print('\n')

# Systemd has a basic syntax for times, such as (5min and 20sec) but
# we need to convert them into seconds only.
def parse_time(time):
    if time.isnumeric():
        return time
    sec = 0
    mem = ""
    what = ""
    letter = False # Used for spliting different time types
    times = [ ]
    for ch in time:
        # Unfortunately, systemd doesn't enforce the use of spaces between
        # different time types, So We need to advanced parsing. Meh
        # Store systemd times as a list into TIMES list
        if ch == " ":
            continue # Skip empty spaces
        if ch.isnumeric():
            if not letter:
                mem += ch
                continue
            else:
                times.append([ what.strip(), mem.strip() ])
                mem += ch # Here's Next entry
                what = "" # Reset what for new entry
                letter = False # Reset letter for new entry
                continue
        if ch.isalpha():
            what += ch
            letter = True
    times.append([ what.strip(), mem.strip() ]) # Catch last entry
    for item in times:
        match item[0]:
            case "μs" | "us" | "usec":
                sec += (float(mem) / 1000000)
            case "ms" | "msec":
                sec += (float(mem) / 1000)
            case "s" | "sec" | "second" | "seconds":
                sec += float(mem)
            case "m" | "min" | "minute" | "minutes":
                sec += (float(mem) * 60)
            case "h" | "hr" | "hour" | "hours":
                sec += (float(mem) * 3600)
            case "d" | "day" | "days":
                sec += (float(mem) * 86400)
            case "w" | "week" | "weeks":
                sec += (float(mem) * 604800)
            case "M" | "month" | "months":
                sec += (float(mem) * 2592000)
            case "y" | "year" | "years":
                # ToDo: Throw a warning if result can't be captured in int type var
                sec += (float(mem) * 31536000)
            case _:
                warning(f"Can't parse given time: {item[1]} {item[0]}")
    return sec

## Parse flags
parser = argparse.ArgumentParser(
        prog='unit_to_srv',
        description='Convert systemd unit files into dinit services',
        epilog='See Usage.md for more information'
)
parser.add_argument('unitfile', help="Systemd unit file path")
parser.add_argument('--quiet', '-q', action='store_true', help="Be quiet about warnings")
args = parser.parse_args()

## Parse systemd unit
# In this stage, We just parse given unit file into a key "map"
with open(args.unitfile, "r", encoding="UTF-8") as file:
    for line in file:
        name = ""
        memory = ""
        if line[0] == "#" or line[0] == ";":
            comments.append(f'#In systemd service unit comment: {line}') # comment
        elif line[0] != "[":
            for ch in line:
                if ch == "=":
                    name = memory
                    memory = ""
                else:
                    memory += ch
            if name: # Ignore empty lines
                input_map.append(key_value_struct(name.strip(), memory.strip()))

## Actual converting
## there is where fun begins :)
# Systemd can watch the forking process to determine pid in "forking" type
# services, but dinit doesn't support this way So PIDFile is mandatory.
# You shuold provide a pid-file for forking (bgprocess) services.
# 0: Isn't bgprocess, 1: Is bgprocess but doesn't have pid-file, 2: correct bgprocess
is_pidfile = 0
# Some systemd services doesn't have type.
has_type = False
for expr in input_map:
    if not expr.key in systemd_ref_map:
        warning(f'Unknown/Unsupported key: {expr.key}')
        continue
    match expr.key:
        case "Documentation":
            continue # no-op
        case "Description":
            comments.append(f'# Description: {expr.value}\n')
        case "Type":
            match expr.value:
                case "simple" | "exec":
                    output_map.append(key_value_struct('type', 'process'))
                case "forking":
                    output_map.append(key_value_struct('type', 'bgprocess'))
                    is_pidfile = 1
                case "oneshot":
                    output_map.append(key_value_struct('type', 'scripted'))
                case "notify":
                    output_map.append(key_value_struct('type', 'process'))
                    warning('''This service use systemd activition protocol
Please change your service to use a proper ready notification protocol:
https://skarnet.org/software/s6/notifywhenup.html''')
                case "dbus":
                    print('\'type=dbus\' isn\'t supported by dinit!')
                    os._exit(1)
            has_type = True
        case "ExecStart":
            output_map.append(key_value_struct('command', expr.value))
        case "ExecStop":
            output_map.append(key_value_struct('stop-command', expr.value))
        case "Wants" | "UpHolds":
            for dep in expr.value.split(" "):
                output_map.append(key_value_struct('waits-for', dep))
        case "Requires" | "Requisite" | "BindsTo" | "PartOf":
            for dep in expr.value.split(" "):
                output_map.append(key_value_struct('depends-on', dep))
        case "WantedBy" | "RequiredBy" | "UpheldBy":
            for dep in expr.value.split(" "):
                output_map.append(key_value_struct('before', dep))
        case "Before":
            for dep in expr.value.split(" "):
                output_map.append(key_value_struct('before', dep))
            warning('Before in dinit has different functionality over systemd')
        case "After":
            for dep in expr.value.split(" "):
                output_map.append(key_value_struct('after', dep))
            warning('After in dinit has different functionality over systemd')
        case "Alias":
            for alias in expr.value.split(" "):
                with open(alias, "w", encoding="UTF-8") as temp:
                    temp.write(f'depends-on = {args.unitfile}.dinit\n')
            print('Service unit has \"Alias\", Creating another service for convering that')
        case "OnSuccess":
            for chain in expr.value.split(" "):
                output_map.append(key_value_struct('chain-to', sdep))
        case "StartLimitBurst":
            output_map.append(key_value_struct('restart-limit-count', expr.value))
        case "StartLimitIntervalSec":
            output_map.append(key_value_struct('restart-limit-interval', expr.value))
        case "PIDFile":
            output_map.append(key_value_struct('pid-file', expr.value))
            is_pidfile = 2
        case "EnvironmentFile":
            output_map.append(key_value_struct('env-file', expr.value))
        case "Restart":
            if expr.value == "true" or expr.value == "false":
                output_map.append(key_value_struct('restart', expr.value))
        case "TimeoutStartSec" | "TimeoutStopSec" | "TimeoutSec":
            if expr.value == "infinity":
                TIME = 0
            else:
                TIME = parse_time(expr.value)
            if expr.value == "TimeoutSec":
                output_map.append(key_value_struct('start-timeout', TIME))
                output_map.append(key_value_struct('stop-timeout', TIME))
            elif "Start" in expr.key:
                output_map.append(key_value_struct('start-timeout', TIME))
            else:
                output_map.append(key_value_struct('stop-timeout', TIME))
        case "User":
            STR = f'{expr.value}'
            output_map.append(key_value_struct('run-as', STR))
        case "Group":
            warning('Setting specific group for execution is not support in Dinit')
            sub_warning('Dinit will use primary group of user', False)
        case "WorkingDirectory":
            output_map.append(key_value_struct('working-dir', expr.value))
        case "LimitCORE":
            output_map.append(key_value_struct('rlimit-core', expr.value))
        case "LimitNOFILE":
            output_map.append(key_value_struct('rlimit-nofile', expr.value))
        case "LimitDATA":
            output_map.append(key_value_struct('rlimit-data', expr.value))
        case "UtmpIdentifier":
            output_map.append(key_value_struct('inittab-line', expr.value))
        case "KillSignal":
            SIG = ""
            match expr.value.removeprefix('SIG'):
                case "HUP" | "INT" | "QUIT" | "KILL" | "USR1" | "USR2" | "TERM" | "CONT" | "STOP" | "INFO":
                    SIG = expr.value.removeprefix('SIG')
                case _:
                    warning(f'{expr.value} isn\'t recognized by Dinit, Trying to resolve it to number')
                    for knownsig in signal.Signals:
                        if expr.value == knownsig.name:
                            SIG = knownsig.value
            if SIG:
                sub_warning(f'Resolved to {SIG}', True)
                output_map.append(key_value_struct('term-signal', expr.value))
            else:
                sub_warning(f'Cannot resolve specifed signal: {expr.value}', True)
        case _:
            print(f'Not implemented key: {expr.key}')
        # ToDo: More

if not has_type:
    output_map.append(key_value_struct('type', 'process')) # Default fall-back type

## Writing output_map into target
with open(pathlib.Path(args.unitfile).name + '.dinit', 'w', encoding="UTF-8") as target:
    for comment in comments:
        target.write(comment)
    for expr in output_map:
        target.write(f'{expr.key} = {expr.value}\n')
    if is_pidfile == 1:
        warning('Service is "forking" type but doesn\'t have any pid-file!, See Usage.md')
        target.write('# Service is "forking" type but doesn\'t have any pid-file!\n')

print('\nConverting service unit to dinit service is completed.')
print('It\'s HIGHLY recommended to modify this generated file to fit your needs')
print('Done!')
