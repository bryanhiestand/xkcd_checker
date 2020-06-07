#!/usr/bin/env python3
"""
Emails the latest comic to the recipient specified in settings.

Checks xkcd's latest comic, using the xkcd API at http://xkcd.com/info.0.json

Project page: https://github.com/bryanhiestand/xkcd_checker

See README.md for more information.
"""

import base64
import datetime
import logging
import os
import sys
from ast import literal_eval

from dotenv import load_dotenv
import requests
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (Attachment, Disposition, FileContent,
                                   FileName, FileType, Mail)

logging.basicConfig(level=20)

xkcd_api_url = 'http://xkcd.com/info.0.json'
history_file = 'xkcd_history.txt'
comic_dir = 'comics'

class Config(object):
    config_prefix = 'XKCD_'

    def __init__(self):
        # load env vars from .env
        load_dotenv()

        self.mail_method = self.get_config_str('MAIL_METHOD')
        self.mail_to = self.get_config_str('MAIL_TO')
        self.mail_from = self.get_config_str('MAIL_FROM')

        # Whether to download the file locally. Required if emailing comic as attachment
        self.download = self.get_config_bool('DOWNLOAD')

        # Whether to mail comic as attachment in addition to <img src=""> html
        # Requires download = True
        self.mail_attachment = self.get_config_bool('MAIL_ATTACHMENT')

        # Sendgrid-specific options
        self.sendgrid_api_key = self.get_config_str('SENDGRID_API_KEY')

        # SMTP-specific options
        self.smtp_server = self.get_config_str('SMTP_SERVER')
        self.smtp_port = self.get_config_str('SMTP_PORT', default='587')
        self.smtp_ttls = self.get_config_bool('SMTP_TTLS')
        self.smtp_username = self.get_config_str('SMTP_USERNAME')
        self.smtp_password = self.get_config_str('SMTP_PASSWORD')

        # Perform basic validation of config from .env
        if self.mail_attachment and not self.download:
            logging.error('XKCD_DOWNLOAD must be enabled before XKCD_MAIL_ATTACHMENT will work')
            sys.exit(1)

        if self.mail_method == 'sendgrid' and not self.sendgrid_api_key:
            logging.error('XKCD_SENDGRID_API_KEY must be set to use sendgrid')

    def get_config_str(self, item, default=None):
        return os.environ.get(f"{self.config_prefix}{item}", default)

    def get_config_bool(self, item):
        """Return a boolean from environment variable config item. Defaults to True."""
        setting = os.environ.get(f"{self.config_prefix}{item}", 'True')
        setting = setting.title()
        return literal_eval(setting)


def check_xkcd():
    """Check xkcd for the latest comic, return dict."""
    try:
        r = requests.get(xkcd_api_url)
        xkcd_dict = r.json()
    except requests.exceptions.RequestException as e:
        logging.critical('xkcd_checker.check_xkcd:Unable to download json. Error: %s' % e)
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
            with open(history_file, mode='w'):
                pass
        except IOError as e:
            logging.critical('xkcd_checker.is_downloaded:Unable to open or create %s. Error: %s' % history_file, e)
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


def download_latest(config, xkcd_dict):
    """Download the latest xkcd image, log to history_file."""
    comic_image_url = xkcd_dict['img']
    comic_filename = get_local_filename(xkcd_dict)
    download_file = os.path.join(comic_dir, comic_filename)

    # if downloading disabled, get filename, skip downloading
    if not config.download:
        logging.info('Downloads disabled, skipping...')
        return comic_filename

    # Ensure images can be saved
    try:
        os.makedirs(comic_dir, exist_ok=True)
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:Unable to open or create %s. Error: %s' % comic_dir, e)
        sys.exit(1)

    # Ensure history file is writable, or script will always re-download image
    try:
        with open(history_file, "at+"):
            pass
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:%s not writable. Error: %s' % history_file, e)
        sys.exit(1)

    # Download the latest image as comic_filename
    try:
        with open(download_file, 'wb') as comic_file:
            comic_image = requests.get(comic_image_url)
            comic_image.raise_for_status()
            comic_file.write(comic_image.content)
            logging.info('Downloaded latest comic %s' % comic_filename)
    except requests.exceptions.RequestException as e:
        logging.critical('xkcd_checker.download_latest:xkcd download failed')
        sys.exit(1)
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:Unable to save %s to %s' % (download_file, comic_dir))
        sys.exit(1)

    return comic_filename


def get_datetime_str(xkcd_dict):
    """Return a pretty datetime string from latest comic data."""
    year = int(xkcd_dict['year'])
    month = int(xkcd_dict['month'])
    day = int(xkcd_dict['day'])
    comic_date = datetime.date(year, month, day)
    return comic_date.strftime("%a %d %b %y")


def email_latest(config, xkcd_dict={}):
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

    if config.mail_method == 'sendgrid':
        try:
            sendgrid_api_key = config.sendgrid_api_key
        except KeyError:
            logging.critical('sendgrid_api_key not found')
            sys.exit(1)

        logging.info('Emailing %s via sendgrid' % xkcd_title)

        client = SendGridAPIClient(sendgrid_api_key)

        message = Mail(
            from_email=config.mail_from,
            to_emails=config.mail_to,
            subject=email_subject,
            html_content=email_html
        )
        
        if config.mail_attachment:
            comic_filename = get_local_filename(xkcd_dict)
            new_comic_path = os.path.join(comic_dir, comic_filename)
            with open(new_comic_path, 'rb') as attach_file:
                data = attach_file.read()
                attach_file.close()
            
            encoded = base64.b64encode(data).decode()


            attachedFile = Attachment(
                FileContent(encoded),
                FileName(comic_filename),
                FileType('image/jpeg'),
                Disposition('attachment')
            )
            message.attachment = attachedFile

        try:
            client.send(message)
            return False
        except Exception as e:
            print(e)
            return e

    elif config.mail_method == 'smtp':
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
            server = config.smtp_server
            port = config.smtp_port
            username = config.smtp_username
            password = config.smtp_password
            ttls = config.smtp_ttls
            mail_to = config.mail_to
            mail_from = config.mail_from

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

            if config.mail_attachment:
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
        logging.warning('No valid mail_method found in config')
        sys.exit(1)


def update_history(xkcd_dict):
    """Append comic number from xkcd_dict to xkcd_history file."""
    comic_number = str(xkcd_dict['num'])

    try:
        with open(history_file, "at") as file:
            # Trailing newline for posix compliance
            file.write(comic_number + '\n')
    except IOError as e:
        logging.critical('xkcd_checker.download_latest:%s became unwritable. Error: %s' % history_file, e)
        sys.exit(1)

    return True


def main():
    """Run functions sequentially to email and log latest xkcd comic."""
    config = Config()

    xkcd_dict = check_xkcd()
    if is_downloaded(xkcd_dict):
        return

    download_latest(config, xkcd_dict)

    # all subfunctions return False if message was sent successfully
    send_error = email_latest(config, xkcd_dict)

    # append to history only if email sent successfully
    if send_error:
        logging.error('Failed to send latest comic. Exiting.')
        sys.exit(1)
    else:
        update_history(xkcd_dict)

if __name__ == '__main__':
    main()
