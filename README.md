# xkcd_checker (Archived)

> **This repository is archived and no longer maintained.**
>
> Please use the actively maintained Rust rewrite instead:
>
> [![ferrous-comics](https://raw.githubusercontent.com/bryanhiestand/ferrous-comics/main/assets/social-preview.svg)](https://github.com/bryanhiestand/ferrous-comics)
>
> **[https://github.com/bryanhiestand/ferrous-comics](https://github.com/bryanhiestand/ferrous-comics)**

Emails the latest comic to the recipient specified in settings.

Checks xkcd's latest comic, using the xkcd api at <http://xkcd.com/info.0.json>

If the latest comic is new, emails the comic to the user and records the comic
as seen. Optionally downloads comics to ./comics/

## Installation Instructions ##

1. clone this repo
1. copy example.env to .env
1. Edit .env with your configuration, filling in your smtp credentials
1. (optional) configure a virtualenv for this project: `mkvirtualenv xkcd_checker`
1. `pip3 install -r requirements.txt`
1. Run from command line: `python3 xkcd_checker.py`
1. Script will create xkcd_history.txt and (if `XKCD_DOWNLOAD=True`) comics/ directory
1. (optional) install as cron job

## Dependencies ##

* python3
* MacOS or Ubuntu (tested on 20.04-24.04)

## Limitations ##

* Emails only the latest comic. Will not catch multiple missed comics since
      last run. (e.g. if last is 1630 and current is 1632, will skip 1631)
* Only accepts one recipient
* Must have file write access in script's directory
* Only supports smtp at this time

## TODO ##

* Support comic backfill (one email for each comic since last run)
* Make email body html prettier
* Test other email providers
* Maybe use tinydb, lmdb, rocksdb, boltdb, or sqlite instead of xkcd_history.txt
