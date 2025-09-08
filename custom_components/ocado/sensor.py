"""Ocado EMail Digester"""
from datetime import timedelta, date, datetime, timezone
import logging
import re
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

from imapclient import IMAPClient
from mailparser import parse_from_bytes
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_EMAIL, CONF_PASSWORD, CONF_IMAP_SERVER,
    CONF_IMAP_PORT, CONF_SSL, CONF_EMAIL_FOLDER, CONF_DAYS_OLD,
    EMAIL_ATTR_FROM, EMAIL_ATTR_SUBJECT,
    EMAIL_ATTR_BODY, EMAIL_ATTR_DATE,
    ATTR_ORDER_EMAIL_DATE, ATTR_ORDER_DELIVERY_DATE, ATTR_ORDER_DELIVERY_TIME, ATTR_ORDER_DELIVERY_COUNTDOWN,
    ATTR_ORDER_EDIT_DATE, ATTR_ORDER_EDIT_TIME, ATTR_ORDER_EDIT_COUNTDOWN)

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=10 * 60)
EMAIL_DOMAIN = 'ocado.com'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_EMAIL): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_DAYS_OLD, default=7): cv.positive_int,
    vol.Required(CONF_IMAP_SERVER, default='imap.gmail.com'): cv.string,
    vol.Required(CONF_IMAP_PORT, default=993): cv.positive_int,
    vol.Required(CONF_SSL, default=True): cv.boolean,
    vol.Required(CONF_EMAIL_FOLDER, default='INBOX'): cv.string,
})

def get_ocado_edit_details(html_content: str) -> dict:
    soup = BeautifulSoup(html_content, 'html.parser')
    edit_details = {'edit_time': None, 'edit_date': None, 'edit_datetime_object': None}

    edit_text_element = soup.find(lambda tag: tag.name == 'td' and 'You can edit this order until' in tag.get_text())
    if edit_text_element:
        full_edit_string = edit_text_element.get_text().strip()
        match = re.search(r'until\s*(\d{1,2}:\d{2}(?:[AP]\.?M\.?)?),\s*(.*)', full_edit_string, re.IGNORECASE)
        if match:
            order_edit_time_str = match.group(1).strip()
            order_edit_date_str = match.group(2).strip().rstrip('.').strip()
            edit_details['edit_date'] = order_edit_date_str
            try:
                combined_datetime_str = f"{order_edit_date_str} {order_edit_time_str}"
                try:
                    edit_datetime_obj = datetime.strptime(combined_datetime_str, '%d %B %Y %I:%M%p')
                except ValueError:
                    edit_datetime_obj = datetime.strptime(combined_datetime_str, '%d %B %Y %H:%M')
                edit_details['edit_datetime_object'] = edit_datetime_obj.replace(tzinfo=ZoneInfo('Europe/London')).astimezone(timezone.utc)
                # Store edit_time in 24-hour format
                edit_details['edit_time'] = edit_datetime_obj.strftime('%H:%M')
            except ValueError as e:
                _LOGGER.warning(f"Parsing error: {e}")
    return edit_details

def get_ocado_delivery_details(html_content: str) -> dict:
    soup = BeautifulSoup(html_content, 'html.parser')
    delivery_details = {
        'delivery_time': None,
        'delivery_date': None,
        'formatted_delivery_time': None,
        'delivery_datetime_object': None,
        ATTR_ORDER_DELIVERY_COUNTDOWN: None,
    }

    delivery_info_td = soup.find(lambda tag: tag.name == 'td' and ('Delivery time:' in tag.get_text() or 'Delivery date:' in tag.get_text()))
    if delivery_info_td:
        text_content = delivery_info_td.get_text().strip()
        time_match = re.search(r'Delivery time:\s*(.*)', text_content)
        if time_match:
            raw_delivery_time_str = time_match.group(1).strip()
            delivery_details['delivery_time'] = raw_delivery_time_str
            time_range_match = re.search(r'Between\s*(\d{1,2}:\d{2}(?:[ap]m)?)\s*and\s*(\d{1,2}:\d{2}(?:[ap]m)?)', raw_delivery_time_str, re.IGNORECASE)
            if time_range_match:
                formatted_times = []
                for time_s in time_range_match.groups():
                    try:
                        time_obj = datetime.strptime(time_s, '%I:%M%p').time()
                        formatted_times.append(time_obj.strftime('%H:%M'))
                    except ValueError:
                        formatted_times = []
                        break
                if formatted_times:
                    delivery_details['formatted_delivery_time'] = f"{formatted_times[0]} - {formatted_times[1]}"
        date_match = re.search(r'Delivery date:\s*([0-9]{1,2}\s+\w+\s+[0-9]{4})', text_content)
        if date_match:
            delivery_details['delivery_date'] = date_match.group(1).strip()
            try:
                delivery_details['delivery_datetime_object'] = datetime.strptime(delivery_details['delivery_date'], '%d %B %Y').date()
            except ValueError:
                pass

        if delivery_details['formatted_delivery_time'] and delivery_details['delivery_date']:
            try:
                now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
                start_time_str = delivery_details['formatted_delivery_time'].split(' - ')[0]
                start_hour, start_minute = map(int, start_time_str.split(':'))
                delivery_start_datetime = datetime.strptime(delivery_details['delivery_date'], '%d %B %Y').replace(hour=start_hour, minute=start_minute, tzinfo=timezone.utc)
                countdown_minutes = int((delivery_start_datetime - now_utc).total_seconds() // 60)
                delivery_details[ATTR_ORDER_DELIVERY_COUNTDOWN] = countdown_minutes
            except Exception as e:
                _LOGGER.warning(f"Countdown calc error: {e}")
    return delivery_details

def check_delivery_edit_status(delivery_datetime_obj, edit_datetime_obj):
    now = datetime.now(timezone.utc)
    edit_status = now < edit_datetime_obj
    
    delivery_end_dt_utc = datetime.combine(
    delivery_datetime_obj,
    datetime.max.time(),
    tzinfo=ZoneInfo('Europe/London')).astimezone(timezone.utc)

    delivery_status = now < delivery_end_dt_utc

    edit_countdown = int((edit_datetime_obj - now).total_seconds() // 60) if edit_status else 0
    return edit_status, delivery_status, edit_countdown

def ocado(email_body: str, subject: str, email_date: datetime) -> dict:
    if subject != 'Confirmation of your order':
        return None

    parsed_attributes = {}
    try:
        edit_details = get_ocado_edit_details(email_body)
        delivery_details = get_ocado_delivery_details(email_body)

        parsed_attributes[ATTR_ORDER_EMAIL_DATE] = email_date.strftime('%A %d %B %Y %H:%M')
        parsed_attributes[ATTR_ORDER_DELIVERY_TIME] = delivery_details['formatted_delivery_time'] or delivery_details['delivery_time']
        parsed_attributes[ATTR_ORDER_EDIT_TIME] = edit_details['edit_time']
        parsed_attributes[ATTR_ORDER_DELIVERY_COUNTDOWN] = delivery_details.get(ATTR_ORDER_DELIVERY_COUNTDOWN)

        edit_date_display = "Not Available"
        delivery_date_display = "Not Available"
        edit_countdown = 0

        if delivery_details['delivery_datetime_object'] and edit_details['edit_datetime_object']:
            edit_status, delivery_status, edit_countdown = check_delivery_edit_status(
                delivery_details['delivery_datetime_object'],
                edit_details['edit_datetime_object']
            )
            if edit_status:
                edit_date_display = edit_details['edit_datetime_object'].strftime('%A %d %b')
            else:
                parsed_attributes[ATTR_ORDER_EDIT_TIME] = 'Not Available'
            if delivery_status:
                delivery_date_display = delivery_details['delivery_datetime_object'].strftime('%A %d %b')
            else:
                parsed_attributes[ATTR_ORDER_DELIVERY_TIME] = ' '

        parsed_attributes[ATTR_ORDER_EDIT_COUNTDOWN] = edit_countdown
        parsed_attributes[ATTR_ORDER_DELIVERY_DATE] = delivery_date_display
        parsed_attributes[ATTR_ORDER_EDIT_DATE] = edit_date_display
        return parsed_attributes

    except Exception as err:
        _LOGGER.error('Ocado process error: %s', err)
        return None

def setup_platform(hass, config, add_entities, discovery_info=None):
    add_entities([EmailEntity(config)], True)

class EmailEntity(Entity):
    def __init__(self, config):
        self._attr = {}
        self.imap_server = config[CONF_IMAP_SERVER]
        self.imap_port = config[CONF_IMAP_PORT]
        self.email_address = config[CONF_EMAIL]
        self.password = config[CONF_PASSWORD]
        self.email_folder = config[CONF_EMAIL_FOLDER]
        self.ssl = config[CONF_SSL]
        self.days_old = int(config[CONF_DAYS_OLD])
        self.flag = [u'SINCE', date.today() - timedelta(days=self.days_old)]
        self._name = 'ocado_tracking'

    def update(self):
        self._attr = {}
        self.flag = [u'SINCE', date.today() - timedelta(days=self.days_old)]
        server = IMAPClient(self.imap_server, use_uid=True, ssl=self.ssl)
        try:
            server.login(self.email_address, self.password)
            server.select_folder(self.email_folder, readonly=True)
            messages = sorted(server.search(self.flag))
            latest_ocado_email_data = None
            for uid in reversed(messages):
                try:
                    message_data = server.fetch([uid], 'RFC822')[uid]
                    mail = parse_from_bytes(message_data[b'RFC822'])
                    email_from = mail.from_[0][1] if mail.from_ else ''
                    if EMAIL_DOMAIN in email_from and mail.subject == 'Confirmation of your order':
                        latest_ocado_email_data = {
                            EMAIL_ATTR_FROM: email_from,
                            EMAIL_ATTR_SUBJECT: mail.subject,
                            EMAIL_ATTR_BODY: mail.body,
                            EMAIL_ATTR_DATE: mail.date,
                        }
                        break
                except Exception as err:
                    _LOGGER.warning('Mail parse error UID %s: %s', uid, err)
        except Exception as err:
            _LOGGER.error('IMAP error: %s', err)
        finally:
            server.logout()

        if latest_ocado_email_data:
            parsed_data = ocado(
                email_body=latest_ocado_email_data[EMAIL_ATTR_BODY],
                subject=latest_ocado_email_data[EMAIL_ATTR_SUBJECT],
                email_date=latest_ocado_email_data[EMAIL_ATTR_DATE]
            )
            if parsed_data:
                self._attr.update(parsed_data)

    @property
    def state(self):
        return self._attr.get(ATTR_ORDER_EDIT_COUNTDOWN, 'unavailable')

    @property
    def name(self):
        return self._name

    @property
    def extra_state_attributes(self):
        return self._attr

    @property
    def icon(self):
        return 'mdi:truck'
