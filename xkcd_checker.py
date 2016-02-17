#!/usr/bin/env python3
"""
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
"""

import datetime
import logging
import os
import requests
import sys
try:
    import xkcd_settings
except ImportError:
    logging.error('Unable to load xkcd_settings.py')
    logging.error('Please create xkcd_settings.py from xkcd_settings.py.example')
    sys.exit(1)
else:
    pass
    # TODO implement xkcd_settings.log_level before module imports?
    # logging.basicConfig(level=xkcd_settings.log_level))

# moved this below settings import and disabled.
# os.chdir(sys.path[0])
logging.basicConfig(level=20)

xkcd_api_url = 'http://xkcd.com/info.0.json'
history_file = 'xkcd_history.txt'
comic_dir = 'comics'


def check_xkcd():
    """Check xkcd for the latest comic, return dict."""
    try:
        r = requests.get(xkcd_api_url)
        xkcd_dict = r.json()
    except requests.exceptions.RequestException as e:
        logging.critical('xkcd_checker.check_xkcd:Unable to download json')
        sys.exit(1)
    else:
        logging.debug('xkcd_checker.check_xkcd:Got xkcd json. Contents follow')

    for k, v in xkcd_dict.items():
        logging.debug('xkcd_checker.check_xkcd:Key: %s' % k)
        logging.debug('xkcd_checker.check_xkcd:Value: %s' % v)

    return xkcd_dict


def is_downloaded(xkcd_dict):
    """Check local datastore to see if latest xkcd is already downloaded."""
    os.chdir(sys.path[0])

    current_xkcd = str(xkcd_dict['num'])
    logging.debug('is_downloaded:current_xkcd %s' % (current_xkcd))

    try:
        # opening with mode a+ causes readlines to fail
        with open(history_file, mode='rt') as f:
            logging.debug('xkcd_checker.is_downloaded:Opened %s' % history_file)
            for line in reversed(f.readlines()):
                line = line.strip()
                logging.debug('is_downloaded:line=%s' % (line))
                if line == current_xkcd:
                    logging.info('xkcd_checker.is_downloaded:xkcd %s already downloaded. Exiting' % current_xkcd)
                    return True
                else:
                    pass
            else:
                logging.info('xkcd_checker.is_downloaded:xkcd %s not found in history' % current_xkcd)
                return False

    except IOError as e:
        try:
            # workaround for ISSUE1
            with open(history_file, mode='w') as f:
                pass
        except IOError as e:
            logging.critical('xkcd_checker.is_downloaded:Unable to open or create %s' % history_file)
            logging.critical('xkcd_checker.is_downloaded:Ensure current working directory is executable')
            sys.exit(1)
        else:
            logging.debug('Created %s' % history_file)
            return False


def get_local_filename(xkcd_dict):
    """Given a dict from the xkcd json, return comic_number-image_name.ext."""
    comic_number = str(xkcd_dict['num'])
    comic_image_url = xkcd_dict['img']
    return '%s-%s' % (comic_number, os.path.basename(comic_image_url))


def download_latest(xkcd_dict):
    """Download the latest xkcd image, log to history_file."""
    comic_image_url = xkcd_dict['img']
    comic_filename = get_local_filename(xkcd_dict)
    download_file = os.path.join(comic_dir, comic_filename)

    # if downloading disabled, get filename, skip downloading
    if not xkcd_settings.download:
        logging.info('Downloads disabled, skipping...')
        return comic_filename

    # Ensure images can be saved
    try:
        os.makedirs(comic_dir, exist_ok=True)
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:Unable to open or create %s' % comic_dir)
        sys.exit(1)

    # Ensure history file is writable, or script will always re-download image
    try:
        with open(history_file, "at+") as file:
            pass
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:%s not writable' % history_file)
        sys.exit(1)

    # Download the latest image as comic_filename
    try:
        with open(download_file, 'wb') as comic_file:
            comic_image = requests.get(comic_image_url)
            comic_image.raise_for_status()
            comic_file.write(comic_image.content)
            logging.info('Downloaded latest comic %s' % comic_filename)
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:Unable to save %s to %s' % (download_file, comic_dir))
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        logging.critical('xkcd_checker.download_latest:xkcd download failed')
        sys.exit(1)

    return comic_filename


def get_datetime_str(xkcd_dict):
    """Return a pretty datetime string from latest comic data."""
    year = int(xkcd_dict['year'])
    month = int(xkcd_dict['month'])
    day = int(xkcd_dict['day'])
    comic_date = datetime.date(year, month, day)
    return comic_date.strftime("%a %d %b %y")


def email_latest(xkcd_dict={}):
    """Email the latest comic to a recipient, optionally include comic as attachment."""
    # TODO reduce mccabe complexity
    datetime_str = get_datetime_str(xkcd_dict)
    xkcd_title = xkcd_dict['safe_title']
    email_subject = 'New xkcd %s: %s from %s' % (xkcd_dict['num'], xkcd_title, datetime_str)
    email_text = '%s: %s' % (xkcd_title, xkcd_dict['img'])
    email_html = '''<html><body>
<h1><a href=\"%s\">%s:<br>
<img title=\"%s\" alt=\"%s\" style=\"display:block\" src=\"%s\" /></a></h1>
''' % (xkcd_dict['img'], xkcd_title, xkcd_title, xkcd_title, xkcd_dict['img'])

    if xkcd_settings.send_method == 'sendgrid':
        try:
            import sendgrid
        except ImportError:
            logging.error('Unable to load sendgrid module')
            logging.error('EXITING:Sendgrid requires sendgrid python module. Try pip3 install sendgrid')
            sys.exit(1)
        else:
            try:
                sendgrid_api_key = xkcd_settings.sendgrid_api_key
            except KeyError:
                logging.critical('sendgrid_api_key not found')
                sys.exit(1)
            else:
                logging.info('Emailing %s via sendgrid' % xkcd_title)

                client = sendgrid.SendGridClient(sendgrid_api_key)
                message = sendgrid.Mail()

                message.add_to(xkcd_settings.mail_to)
                message.set_from(xkcd_settings.mail_from)
                message.set_subject(email_subject)
                message.set_html(email_html)

                if xkcd_settings.mail_attachment:
                    comic_filename = get_local_filename(xkcd_dict)
                    new_comic_path = os.path.join(comic_dir, comic_filename)
                    with open(new_comic_path, 'rb') as attach_file:
                        message.add_attachment(comic_filename, attach_file)

                result = client.send(message)
                # result is a tuple: (200, b'{"message":"success"}')
                if b'success' in result[1]:
                    return False
                else:
                    return result

    elif xkcd_settings.send_method == 'smtp':
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.image import MIMEImage
            import smtplib

        except ImportError:
            logging.error('Unable to load smtplib or email.mime module. This should not happen')
            sys.exit(1)
        else:
            # Get all required external vars
            server = xkcd_settings.smtp_server
            port = xkcd_settings.smtp_port
            username = xkcd_settings.smtp_username
            password = xkcd_settings.smtp_password
            ttls = xkcd_settings.smtp_ttls
            mail_to = xkcd_settings.mail_to
            mail_from = xkcd_settings.mail_from

            # Craft MIMEMultipart message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = email_subject
            msg['From'] = mail_from
            msg['To'] = mail_to
            msg_txt = email_text
            msg_html = email_html

            # MIME finagling to allow gmail inline from stackoverflow DataTx
            # http://stackoverflow.com/questions/882712/sending-html-email-using-python
            part1 = MIMEText(msg_txt, _subtype='plain')
            part2 = MIMEText(msg_html, _subtype='html')
            msg.attach(part1)
            msg.attach(part2)

            if xkcd_settings.mail_attachment:
                comic_filename = get_local_filename(xkcd_dict)
                new_comic_path = os.path.join(comic_dir, comic_filename)
                with open(new_comic_path, 'rb') as attach_file:
                    attachment = MIMEImage(attach_file.read())
                    attachment.add_header('Content-Disposition', 'attachment', filename=comic_filename)
                    msg.attach(attachment)

            logging.info('Emailing %s via smtp' % xkcd_title)

            # TODO add error handling for all possible smtplib failures
            smtp_object = smtplib.SMTP(server, port)
            smtp_object.ehlo()
            if ttls:
                smtp_object.starttls()
            try:
                smtp_object.login(username, password)
            except smtplib.SMTPAuthenticationError as e:
                logging.error('email_latest:SMTPAuthenticationError. Exiting.')
                sys.exit(1)

            smtp_error = smtp_object.sendmail(mail_from, mail_to, msg.as_string())
            return smtp_error

    else:
        logging.warning('No valid send_method found in xkcd_settings')
        sys.exit(1)


def check_settings():
    """Perform basic validation on xkcd_settings.py."""
    if xkcd_settings.mail_attachment and not xkcd_settings.download:
        logging.error('mail_attachment option requires download = True')
        sys.exit(1)

    if xkcd_settings.send_method == 'sendgrid' and not xkcd_settings.sendgrid_api_key:
        logging.error('sendgrid support requires sendgrid_api_key')
        sys.exit(1)


def update_history(xkcd_dict):
    """Append comic number from xkcd_dict to xkcd_history file."""
    comic_number = str(xkcd_dict['num'])

    try:
        with open(history_file, "at") as file:
            # Trailing newline for posix compliance
            file.write(comic_number + '\n')
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:%s became unwritable.' % history_file)
        sys.exit(1)

    return True


def main():
    """Run functions sequentially to email and log latest xkcd comic."""
    check_settings()

    xkcd_dict = check_xkcd()

    if is_downloaded(xkcd_dict):
        return

    download_latest(xkcd_dict)

    # all subfunctions return False if message was sent successfully
    send_error = email_latest(xkcd_dict=xkcd_dict)

    # append to history only if email sent successfully
    if send_error:
        logging.error('Failed to send latest comic. Exiting.')
        sys.exit(1)
    else:
        update_history(xkcd_dict)

if __name__ == '__main__':
    main()
