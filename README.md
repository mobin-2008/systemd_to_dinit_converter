unit_to_srv: Covnert systemd unit into dinit service
----------------------------------------------------

This is a python script (Requires python 3.10 or later) for converting systemd units
into dinit services.

Generated services need to be modified and checked with `dinitcheck` to be usable. See
`dinit-service(5)` man-page.

## Basic Usage
```
./unit_to_srv.py <unit-file> [-q, --quiet] [-h]
```

ToDo:

- Create Usage.md file
