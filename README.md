Emails the latest comic to the recipient specified in settings.

Checks xkcd's latest comic, using the xkcd api at http://xkcd.com/info.0.json

If the latest comic is new, emails the comic to the user and records the comic as seen. Optionally downloads comics to ./comics/

### Installation Instructions ###
1. clone this repo
2. copy xkcd_settings.py.example to xkcd_settings.py
3. Edit xkcd_settings.py, filling in your send_method (smtp or sendgrid), username, password, or api key
4. Run from command line: python3 xkcd_checker.py
5. Script will create xkcd_history.txt and (if downloading) comics/ directory
6. Repeat run to ensure duplicates not sent
7. If successful, install as cron job. I recommend hourly

### Dependencies ###
* python3
* builtin datetime, logging, os, requests, and sys python3 modules
* if using sendgrid, sendgrid module installed for python3
* if using smtp, builtin smtplib, email.mime python3 modules
* xkcd_settings.py correctly filled out (see xkcd_settings.example)

### Limitations ###
* Emails only the latest comic. Will not catch multiple missed comics since
      last run. (e.g. if last is 1630 and current is 1632, will skip 1631)
* Will break when xkcd hits 16,300 comics
* Only accepts one recipient
* Must have file write access in script's directory
* Only supports sendgrid and smtp at this time

### TODO ###
* Support comic backfill (one email for each comic since last run)
* Use proper config loading instead of xkcd_settings.py import
* Make email body html prettier
* Test other email providers
* Maybe use sqlite for fun
