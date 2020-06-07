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

logging.basicConfig(level=20)

xkcd_api_url = 'https://xkcd.com/info.0.json'
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


class Emailer(object):
    def __init__(self, config, comic):
        self.config = config
        self.comic = comic
        self.comic_filename = get_local_filename(comic)

        self.datetime_str = get_datetime_str(comic)
        self.xkcd_title = comic['safe_title']
        self.email_subject = f"New xkcd {comic['num']}: {self.xkcd_title} from {self.datetime_str}"
        self.email_text = f"{self.xkcd_title}: {comic['img']}"
        self.email_html = f"""
<html><body>
<h1>
<a href="{comic['img']}">{self.xkcd_title}<img title="{self.xkcd_title}" alt="{self.xkcd_title}" style="display:block" src="{comic['img']}" /></a>
</h1>
<br>
<br>
Mailed by <a href="https://github.com/bryanhiestand/xkcd_checker">xkcd_checker</a>
</body>
"""

    def mail_sendgrid(self):
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import (Attachment, Disposition, FileContent,
                                        FileName, FileType, Mail)

        logging.info(f"Emailing {self.xkcd_title} via sendgrid")

        client = SendGridAPIClient(self.config.sendgrid_api_key)

        message = Mail(
            from_email=self.config.mail_from,
            to_emails=self.config.mail_to,
            subject=self.email_subject,
            html_content=self.email_html
        )
        
        if self.config.mail_attachment:
            new_comic_path = os.path.join(comic_dir, self.comic_filename)
            with open(new_comic_path, 'rb') as attach_file:
                data = attach_file.read()
                attach_file.close()
            
            encoded = base64.b64encode(data).decode()

            attachedFile = Attachment(
                FileContent(encoded),
                FileName(self.comic_filename),
                FileType('image/jpeg'),
                Disposition('attachment')
            )
            message.attachment = attachedFile

        client.send(message)

    def mail_smtp(self):
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.image import MIMEImage
        import smtplib

        # FIXME: ttls defined but unused
        ttls = self.config.smtp_ttls

        # Craft MIMEMultipart message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = self.email_subject
        msg['From'] = self.config.mail_from
        msg['To'] = self.config.mail_to
        msg_txt = self.email_text
        msg_html = self.email_html

        # MIME finagling to allow gmail inline from stackoverflow DataTx
        # http://stackoverflow.com/questions/882712/sending-html-email-using-python
        part1 = MIMEText(msg_txt, _subtype='plain')
        part2 = MIMEText(msg_html, _subtype='html')
        msg.attach(part1)
        msg.attach(part2)

        if self.config.mail_attachment:
            comic_filename = get_local_filename(self.comic)
            new_comic_path = os.path.join(comic_dir, comic_filename)
            with open(new_comic_path, 'rb') as attach_file:
                attachment = MIMEImage(attach_file.read())
                attachment.add_header('Content-Disposition', 'attachment', filename=comic_filename)
                msg.attach(attachment)

        logging.info(f'Emailing {self.xkcd_title} via SMTP')

        smtp_object = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port)
        smtp_object.ehlo()
        if ttls:
            smtp_object.starttls()
        if self.config.smtp_username or self.config.smtp_password:
            smtp_object.login(self.config.smtp_username, self.config.smtp_password)

        smtp_object.sendmail(self.config.mail_from, self.config.mail_to, msg.as_string())


def check_xkcd():
    """Check xkcd for the latest comic, return dict."""
    retry_delay_minutes = 1 # fixme: 15

    try:
        r = requests.get(xkcd_api_url)
        comic = r.json()
    except requests.exceptions.RequestException as e:
        logging.critical(f'xkcd_checker.check_xkcd:Unable to download json. Error: {e}')
        logging.critical(f'sleeping {retry_delay_minutes} minute(s)')

        import time
        time.sleep(60*retry_delay_minutes)
        try:
            r = requests.get(xkcd_api_url)
            comic = r.json()
        except requests.exceptions.RequestException as e:
            logging.critical(f'still unable to download after one retry. quitting. error {e}')
            sys.exit(1)
    else:
        logging.debug('Got xkcd json. Contents follow')

    for k, v in comic.items():
        logging.debug(f'Latest XKCD Key: {k}')
        logging.debug(f'Latest XKCD Value: {v}')

    return comic


def is_downloaded(comic):
    """Check local datastore to see if latest xkcd is already downloaded."""
    os.chdir(sys.path[0])

    current_xkcd = str(comic['num'])
    logging.debug(f'is_downloaded:current_xkcd {current_xkcd}')

    try:
        # opening with mode a+ causes readlines to fail
        with open(history_file, mode='rt') as f:
            logging.debug(f'xkcd_checker.is_downloaded:Opened {history_file}')
            for line in reversed(f.readlines()):
                line = line.strip()
                logging.debug(f'is_downloaded:line={line}')
                if line == current_xkcd:
                    logging.info(f'xkcd_checker.is_downloaded:xkcd {current_xkcd} already downloaded. Exiting')
                    return True
                else:
                    pass
            else:
                logging.info(f'xkcd_checker.is_downloaded:xkcd {current_xkcd} not found in history')
                return False

    except IOError as e:
        try:
            # workaround for ISSUE1
            with open(history_file, mode='w'):
                pass
        except IOError as e:
            logging.critical(f'xkcd_checker.is_downloaded:Unable to open or create {history_file}. Error: {e}')
            logging.critical('xkcd_checker.is_downloaded:Ensure current working directory is executable')
            sys.exit(1)
        else:
            logging.debug(f'Created {history_file}')
            return False


def get_local_filename(comic):
    """Given a dict from the xkcd json, return comic_number-image_name.ext."""
    comic_number = str(comic['num'])
    comic_image_url = comic['img']
    return f'{comic_number}-{os.path.basename(comic_image_url)}'


def download_latest(config, comic):
    """Download the latest xkcd image, log to history_file."""
    comic_image_url = comic['img']
    comic_filename = get_local_filename(comic)
    download_file = os.path.join(comic_dir, comic_filename)

    # if downloading disabled, get filename, skip downloading
    if not config.download:
        logging.info('Downloads disabled, skipping...')
        return comic_filename

    # Ensure images can be saved
    try:
        os.makedirs(comic_dir, exist_ok=True)
    except IOError as e:
        logging.critical(f'xkcd_checker.download_latest:Unable to open or create {comic_dir}. Error: {e}')
        sys.exit(1)

    # Ensure history file is writable, or script will always re-download image
    try:
        with open(history_file, "at+"):
            pass
    except IOError as e:
        logging.critical(f'xkcd_checker.download_latest:{history_file} not writable. Error: {e}')
        sys.exit(1)

    # Download the latest image as comic_filename
    try:
        with open(download_file, 'wb') as comic_file:
            comic_image = requests.get(comic_image_url)
            comic_image.raise_for_status()
            comic_file.write(comic_image.content)
            logging.info(f'Downloaded latest comic {comic_filename}')
    except requests.exceptions.RequestException as e:
        logging.critical('xkcd_checker.download_latest:xkcd download failed')
        sys.exit(1)
    except IOError as e:
        logging.critical(f'xkcd_checker.download_latest:Unable to save {download_file} to {comic_dir}')
        sys.exit(1)

    return comic_filename


def get_datetime_str(comic):
    """Return a pretty datetime string from latest comic data."""
    year = int(comic['year'])
    month = int(comic['month'])
    day = int(comic['day'])
    comic_date = datetime.date(year, month, day)
    return comic_date.strftime("%a %d %b %y")

def update_history(comic):
    """Append comic number from comic to xkcd_history file."""
    comic_number = str(comic['num'])

    try:
        with open(history_file, "at") as file:
            # Trailing newline for posix compliance
            file.write(comic_number + '\n')
    except IOError as e:
        logging.critical(f'xkcd_checker.download_latest:{history_file} became unwritable. Error: {e}')
        sys.exit(1)

    return True


def main():
    """Run functions sequentially to email and log latest xkcd comic."""
    config = Config()

    comic = check_xkcd()
    if is_downloaded(comic):
        return

    download_latest(config, comic)

    emailer = Emailer(config, comic)
    if config.mail_method == 'sendgrid':
        emailer.mail_sendgrid()

    if config.mail_method == 'smtp':
        emailer.mail_smtp()

    update_history(comic)
    # TODO: create history object and methods instead

if __name__ == '__main__':
    main()
